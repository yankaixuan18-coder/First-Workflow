"""
Amazon Category Research Tool — Flask entry point.

Run with: python main.py
Then open http://localhost:5000 in your browser.
"""
import json
import logging
import os
import queue
import threading
import uuid
from datetime import datetime

from flask import Flask, Response, jsonify, render_template, request, send_file
from flask import stream_with_context

# Load .env before importing config
from dotenv import load_dotenv
load_dotenv()

import config
from browser_automation import BrowserController
from amazon_scraper import (
    build_search_url,
    build_paginated_url,
    is_category_url,
    parse_search_results,
    parse_product_detail,
)
from exporters.excel_exporter import export as export_excel, generate_output_filename
from extension_adapters.seller_sprite_adapter import SellerSpriteAdapter

_ss_adapter = SellerSpriteAdapter()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Bump this whenever collection logic changes so logs identify the running code.
BUILD_VERSION = "2026-06-05-stealth-v6"

# -------------------------------------------------------------------------
# In-memory task store
# -------------------------------------------------------------------------
# task_id -> {status, log_queue, log, products, excel_path, error}
tasks: dict = {}
tasks_lock = threading.Lock()


def _new_task() -> str:
    task_id = str(uuid.uuid4())
    # Per-task log file so the user can review / share the full operation log
    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(
        log_dir, f"task_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{task_id[:8]}.log"
    )
    with tasks_lock:
        tasks[task_id] = {
            "status": "running",       # running | done | error
            "log": [],                 # list of log strings (for /status fallback)
            "log_queue": queue.Queue(),# live queue for SSE
            "products": [],
            "excel_path": None,
            "error": None,
            "log_path": log_path,      # full operation log on disk
            "resume_event": threading.Event(),  # set by /resume to continue past pause
        }
    return task_id


def _log(task_id: str, message: str):
    """Append a log message to the list, the live queue, and the log file."""
    timestamp = datetime.now().strftime("%H:%M:%S")
    line = f"[{timestamp}] {message}"
    with tasks_lock:
        task = tasks.get(task_id)
        if not task:
            return
        task["log"].append(line)
        task["log_queue"].put(line)
        log_path = task.get("log_path")
    # Write to file outside the lock
    if log_path:
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass
    logger.info(f"[{task_id[:8]}] {message}")


def _field_summary(product: dict, fields: list) -> str:
    """Return a compact "✓标签 / ✗标签" summary for the given fields."""
    parts = []
    for key, label in fields:
        val = product.get(key, "")
        if val:
            preview = str(val).replace("\n", " ")[:18]
            parts.append(f"✓{label}={preview}")
        else:
            parts.append(f"✗{label}")
    return "  ".join(parts)


def _finish(task_id: str, excel_path: str, products: list):
    with tasks_lock:
        task = tasks.get(task_id)
        if not task:
            return
        task["status"] = "done"
        task["excel_path"] = excel_path
        task["products"] = products
        task["log_queue"].put("STATUS:done")
        task["log_queue"].put(None)   # sentinel — SSE stream ends


def _fail(task_id: str, error: str):
    with tasks_lock:
        task = tasks.get(task_id)
        if not task:
            return
        task["status"] = "error"
        task["error"] = error
        task["log_queue"].put(f"ERROR: {error}")
        task["log_queue"].put("STATUS:error")
        task["log_queue"].put(None)


# -------------------------------------------------------------------------
# Collection worker (runs in a background thread)
# -------------------------------------------------------------------------

def run_collection(task_id: str, params: dict):
    """
    Main data collection worker executed in a background thread.

    params keys:
        keyword_or_url  str
        marketplace     str  (key from config.MARKETPLACES)
        max_pages       int
        max_products    int
        fetch_details   bool
        chrome_user_data_dir  str
        chrome_profile  str
    """
    keyword_or_url: str = params.get("keyword_or_url", "").strip()
    marketplace_key: str = params.get("marketplace", "amazon.com")
    max_pages: int = int(params.get("max_pages", config.MAX_PAGES_DEFAULT))
    max_products: int = int(params.get("max_products", config.MAX_PRODUCTS_DEFAULT))
    fetch_details: bool = bool(params.get("fetch_details", False))
    manual_prepare: bool = bool(params.get("manual_prepare", False))
    chrome_user_data_dir: str = params.get(
        "chrome_user_data_dir",
        os.environ.get("CHROME_USER_DATA_DIR", config.get_default_chrome_user_data_dir()),
    )
    chrome_profile: str = params.get(
        "chrome_profile",
        os.environ.get("CHROME_PROFILE", config.DEFAULT_CHROME_PROFILE),
    )

    marketplace_url = config.MARKETPLACES.get(marketplace_key, "https://www.amazon.com")
    all_products: list = []
    browser: BrowserController | None = None

    try:
        with tasks_lock:
            log_path = tasks.get(task_id, {}).get("log_path", "")
        _log(task_id, f"代码版本 / Build: {BUILD_VERSION}")
        _log(task_id, f"日志文件 / Log file: {log_path}")
        _log(task_id, f"采集设置 / Settings: 最多 {max_pages} 页 / {max_products} 个商品，"
                      f"详情页={'开启 ON' if fetch_details else '关闭 OFF'} (fetch_details={fetch_details!r})")
        if not fetch_details:
            _log(task_id, "⚠️ 详情页已关闭！将只采集搜索页基础数据，"
                          "无法获取卖家精灵数据/卖点/图片/描述/BSR。")
            _log(task_id, "   如需这些数据，请返回第2步开启「详情页」开关。")
        _log(task_id, f"初始化浏览器 / Initializing browser …")
        _log(task_id, f"Edge profile: {chrome_user_data_dir} [{chrome_profile}]")

        browser = BrowserController(
            chrome_user_data_dir=chrome_user_data_dir,
            chrome_profile=chrome_profile,
            headless=False,
        )
        browser.launch()
        _log(task_id, "浏览器启动成功 / Browser launched successfully.")

        # Manual preparation pause: open a product page first so the user can
        # confirm the 卖家精灵 panel appears (and log in if needed), then click
        # "继续采集" in the UI before automated collection begins.
        if manual_prepare and fetch_details:
            prep_url = f"{marketplace_url}/s?k={keyword_or_url}" if not (
                keyword_or_url.startswith("http")) else keyword_or_url
            try:
                browser.navigate(prep_url)
            except Exception:
                pass
            _log(task_id, "⏸️ 已暂停 / PAUSED: 请在弹出的 Edge 窗口里确认卖家精灵面板已出现"
                          "（如未登录请先登录），然后回到本页点击「继续采集」。")
            with tasks_lock:
                tasks[task_id]["status"] = "waiting"
                tasks[task_id]["log_queue"].put("STATUS:waiting")
                ev = tasks[task_id]["resume_event"]
            # Wait up to 10 minutes for the user to resume
            resumed = ev.wait(timeout=600)
            with tasks_lock:
                tasks[task_id]["status"] = "running"
            if resumed:
                _log(task_id, "▶️ 继续采集 / Resumed by user.")
            else:
                _log(task_id, "▶️ 等待超时，自动继续 / Resume timed out, continuing.")

        # Determine whether input is a URL or a keyword
        if keyword_or_url.startswith("http://") or keyword_or_url.startswith("https://"):
            # Reject individual product pages — tool only works on search/category pages
            if "/dp/" in keyword_or_url or "/gp/product/" in keyword_or_url:
                _log(task_id, "❌ 错误 / Error: 请输入搜索关键词或搜索结果页面链接，不支持单个商品详情页链接（含 /dp/）。")
                _log(task_id, "   提示 / Tip: 例如输入关键词 'camping cot'，或粘贴 Amazon 搜索结果页链接（含 /s?k=）。")
                tasks[task_id]["status"] = "error"
                return
            base_url = keyword_or_url
            is_keyword = False
            _log(task_id, f"模式: URL采集 / Mode: URL scraping — {base_url}")
        else:
            base_url = None
            is_keyword = True
            _log(task_id, f"模式: 关键词搜索 / Mode: keyword search -- \"{keyword_or_url}\" on {marketplace_url}")

        for page_num in range(1, max_pages + 1):
            if is_keyword:
                page_url = build_search_url(keyword_or_url, marketplace_url, page_num)
            else:
                page_url = build_paginated_url(base_url, page_num)

            _log(task_id, f"第 {page_num} 页 / Page {page_num}: {page_url}")

            try:
                browser.navigate(page_url)
            except Exception as nav_err:
                _log(task_id, f"  导航警告 / Navigation warning: {nav_err}")
                # Continue anyway — the page may still be parseable

            browser.scroll_to_bottom()
            html = browser.get_page_html()

            page_products = parse_search_results(html, page_url, page_num)
            _log(task_id, f"  解析到 {len(page_products)} 个商品 / Parsed {len(page_products)} products")

            if not page_products:
                _log(task_id, "  未找到商品，停止翻页 / No products found, stopping pagination.")
                break

            # Optionally fetch detail pages for richer data
            if fetch_details:
                _log(task_id, f"  开始逐个打开详情页 / Opening detail pages "
                              f"({min(len(page_products), max_products - len(all_products))} 个)…")
                for idx, product in enumerate(page_products):
                    if len(all_products) + idx >= max_products:
                        break
                    detail_url = product.get("product_url", "")
                    if not detail_url or not product.get("asin"):
                        _log(task_id, f"    跳过 / Skip (缺少URL或ASIN): "
                                      f"asin={product.get('asin','')!r} url={detail_url!r}")
                        continue
                    try:
                        _log(task_id, f"  详情页 {idx+1}/{len(page_products)}: {product['asin']}")
                        browser.navigate(detail_url)
                        browser.scroll_to_bottom()

                        # Wait for the 卖家精灵 overlay to inject before reading
                        _log(task_id, "    等待卖家精灵插件加载 / Waiting for SellerSprite …")
                        ss_ready = browser.wait_for_seller_sprite(
                            timeout_s=config.EXTENSION_WAIT_TIMEOUT,
                            settle_s=config.EXTENSION_SETTLE_DELAY,
                            poll_s=config.EXTENSION_POLL_INTERVAL,
                        )
                        if ss_ready:
                            _log(task_id, "    ✅ 插件已加载 / SellerSprite detected")
                        else:
                            _log(task_id, "    ⚠️ 未检测到插件数据 / SellerSprite not detected "
                                          "(未安装/未登录/加载超时)")

                        detail_html = browser.get_page_html()
                        detail_data = parse_product_detail(detail_html, product["asin"])
                        # Merge detail data into product dict (detail wins for non-empty values)
                        for key, val in detail_data.items():
                            if val:
                                product[key] = val

                        # Log which key detail fields were captured
                        _log(task_id, "    详情页字段 / Detail fields: "
                             + _field_summary(product, [
                                 ("title", "标题"), ("price", "价格"),
                                 ("bsr", "BSR"), ("listing_date", "上架"),
                                 ("bullet_points", "卖点"),
                                 ("all_image_urls", "图片"),
                                 ("product_description", "描述"),
                             ]))

                        # Read SellerSprite extension overlay from the live page
                        if ss_ready:
                            ss_data = _ss_adapter.extract_sync(browser.get_page(), product["asin"])
                            for key, val in ss_data.items():
                                if val:
                                    product[key] = val
                            _log(task_id, "    插件字段 / Plugin fields: "
                                 + _field_summary(product, [
                                     ("ss_monthly_sales_parent", "月销量"),
                                     ("ss_monthly_revenue", "销售额"),
                                     ("ss_fba_fee", "FBA费"),
                                     ("ss_gross_margin", "毛利率"),
                                     ("ss_total_traffic", "流量"),
                                 ]))
                        browser.wait(config.REQUEST_DELAY_MIN, config.REQUEST_DELAY_MAX)
                    except Exception as detail_err:
                        _log(task_id, f"    详情页错误 / Detail page error: {detail_err}")

            # Only keep up to max_products from this page
            remaining = max_products - len(all_products)
            all_products.extend(page_products[:remaining])
            total = len(all_products)
            _log(task_id, f"  累计采集 / Total collected: {total} 个商品")

            if total >= max_products:
                _log(task_id, f"已达到最大采集数量 {max_products}，停止 / Reached max {max_products}, stopping.")
                break

            if page_num < max_pages:
                browser.wait(config.REQUEST_DELAY_MIN, config.REQUEST_DELAY_MAX)

        # Trim to max_products
        all_products = all_products[:max_products]
        _log(task_id, f"采集完成 / Collection complete. 共 {len(all_products)} 个商品。")

        # Export to Excel
        _log(task_id, "正在导出 Excel / Exporting to Excel …")
        output_path = generate_output_filename(keyword_or_url, config.OUTPUT_DIR)
        export_excel(all_products, output_path)
        _log(task_id, f"Excel 已保存 / Excel saved: {os.path.basename(output_path)}")

        _finish(task_id, output_path, all_products)

    except RuntimeError as rte:
        # RuntimeError from BrowserController carries user-friendly messages
        error_msg = str(rte)
        _log(task_id, f"错误 / Error: {error_msg}")
        _fail(task_id, error_msg)
    except Exception as exc:
        import traceback
        tb = traceback.format_exc()
        _log(task_id, f"意外错误 / Unexpected error: {exc}")
        logger.error(tb)
        _fail(task_id, str(exc))
    finally:
        if browser is not None:
            try:
                browser.close()
                _log(task_id, "浏览器已关闭 / Browser closed.")
            except Exception:
                pass


# -------------------------------------------------------------------------
# Flask routes
# -------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template(
        "index.html",
        marketplaces=config.MARKETPLACES,
        default_chrome_dir=config.get_default_chrome_user_data_dir(),
        default_profile=config.DEFAULT_CHROME_PROFILE,
        max_pages_default=config.MAX_PAGES_DEFAULT,
        max_products_default=config.MAX_PRODUCTS_DEFAULT,
        build_version=BUILD_VERSION,
    )


@app.route("/start", methods=["POST"])
def start():
    """Start a new collection task. Returns {task_id}."""
    data = request.get_json(force=True, silent=True) or {}

    keyword_or_url = data.get("keyword_or_url", "").strip()
    if not keyword_or_url:
        return jsonify({"error": "keyword_or_url is required"}), 400

    task_id = _new_task()
    params = {
        "keyword_or_url": keyword_or_url,
        "marketplace": data.get("marketplace", "amazon.com"),
        "max_pages": data.get("max_pages", config.MAX_PAGES_DEFAULT),
        "max_products": data.get("max_products", config.MAX_PRODUCTS_DEFAULT),
        "fetch_details": data.get("fetch_details", False),
        "manual_prepare": data.get("manual_prepare", False),
        "chrome_user_data_dir": data.get(
            "chrome_user_data_dir",
            os.environ.get("CHROME_USER_DATA_DIR", config.get_default_chrome_user_data_dir()),
        ),
        "chrome_profile": data.get(
            "chrome_profile",
            os.environ.get("CHROME_PROFILE", config.DEFAULT_CHROME_PROFILE),
        ),
    }

    thread = threading.Thread(
        target=run_collection,
        args=(task_id, params),
        daemon=True,
        name=f"collector-{task_id[:8]}",
    )
    thread.start()

    return jsonify({"task_id": task_id})


@app.route("/progress/<task_id>")
def progress(task_id: str):
    """
    Server-Sent Events stream of log lines for the given task.
    Each message is a plain text line (event.data in JavaScript).
    The stream ends when the task completes or errors.
    """
    with tasks_lock:
        task = tasks.get(task_id)
    if not task:
        return jsonify({"error": "task not found"}), 404

    log_queue = task["log_queue"]

    def generate():
        while True:
            try:
                message = log_queue.get(timeout=30)
            except queue.Empty:
                # Send a keep-alive comment to prevent proxy timeouts
                yield "data: \n\n"
                continue

            if message is None:
                # Sentinel: stream is done
                break
            yield f"data: {message}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.route("/status/<task_id>")
def status(task_id: str):
    """Return current task status as JSON (polling fallback)."""
    with tasks_lock:
        task = tasks.get(task_id)
    if not task:
        return jsonify({"error": "task not found"}), 404

    return jsonify({
        "status": task["status"],
        "product_count": len(task["products"]),
        "error": task["error"],
        "log_tail": task["log"][-20:],  # last 20 log lines
    })


@app.route("/results/<task_id>")
def results(task_id: str):
    """Return collected products as JSON for the on-screen preview table."""
    with tasks_lock:
        task = tasks.get(task_id)
    if not task:
        return jsonify({"error": "task not found"}), 404

    # Key fields for a compact preview (full data is in the Excel export)
    preview_fields = [
        "asin", "title", "brand", "price", "rating", "review_count",
        "fulfillment", "seller_sprite_monthly_sales", "bsr",
        "main_image_url", "product_url", "page_number",
    ]
    rows = [
        {f: (p.get(f, "") or "") for f in preview_fields}
        for p in task["products"]
    ]

    return jsonify({
        "status": task["status"],
        "count": len(rows),
        "products": rows,
    })


@app.route("/download/<task_id>")
def download(task_id: str):
    """Download the Excel file produced by a completed task."""
    with tasks_lock:
        task = tasks.get(task_id)
    if not task:
        return jsonify({"error": "task not found"}), 404

    excel_path = task.get("excel_path")
    if not excel_path or not os.path.exists(excel_path):
        return jsonify({"error": "Excel file not ready or not found"}), 404

    return send_file(
        excel_path,
        as_attachment=True,
        download_name=os.path.basename(excel_path),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@app.route("/resume/<task_id>", methods=["POST"])
def resume(task_id: str):
    """Resume a task that is paused at the manual-prepare step."""
    with tasks_lock:
        task = tasks.get(task_id)
        if not task:
            return jsonify({"error": "task not found"}), 404
        ev = task.get("resume_event")
    if ev:
        ev.set()
    return jsonify({"ok": True})


@app.route("/download-log/<task_id>")
def download_log(task_id: str):
    """Download the full operation log file for a task."""
    with tasks_lock:
        task = tasks.get(task_id)
    if not task:
        return jsonify({"error": "task not found"}), 404

    log_path = task.get("log_path")
    if not log_path or not os.path.exists(log_path):
        return jsonify({"error": "log file not found"}), 404

    return send_file(
        log_path,
        as_attachment=True,
        download_name=os.path.basename(log_path),
        mimetype="text/plain",
    )


# -------------------------------------------------------------------------
# Entry point
# -------------------------------------------------------------------------

if __name__ == "__main__":
    os.makedirs(config.OUTPUT_DIR, exist_ok=True)
    print("Amazon Category Research Tool")
    print("Open http://localhost:5000 in your browser.")
    print("Press Ctrl+C to stop.")
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)

"""
SellerSprite (卖家精灵) extension adapter — sync version.

Reads the overlay panel injected by 卖家精灵 on Amazon product detail pages.

Strategy: grab the innerText of the tightest container that holds the panel,
then parse every field with regex. This is far more robust than chasing
SellerSprite's class names, which change between extension versions.

Returned keys are a mix of:
  * SellerSprite-only metrics (ss_*) — sales, revenue, fee, margin, traffic
  * canonical product keys (seller_name, bsr, item_weight, …) so the values
    fill the existing Excel columns. main.py merges these into the product
    dict only when non-empty, so they never overwrite good Amazon data.

All fields return "" when the panel is absent.
"""
import logging
import re

from .base_adapter import BaseExtensionAdapter

logger = logging.getLogger(__name__)

# Markers that reliably appear together inside the SellerSprite panel.
_PANEL_MARKERS = ["近30天销量", "FBA费用", "毛利率"]

# JS that returns the innerText of the WHOLE SellerSprite panel.
#
# Strategy: find a small element containing "FBA费用" (unique to the panel),
# then climb up to the panel root — the nearest ancestor that also contains
# "ASIN" plus a metric marker. Climbing UP is essential: the upper metric rows
# (近30天销量/FBA费用/毛利率) and the lower rows (配送时长/包装尺寸/上架时间/流量词)
# live in sibling sub-divs, so the *tightest* container with only the upper
# markers would truncate the bottom half of the panel.
_JS_GET_PANEL = """() => {
    const all = Array.from(document.querySelectorAll('*'));
    // Anchor on a leaf-ish element that mentions FBA费用 (panel-only label)
    let marker = null;
    for (const el of all) {
        const t = el.textContent || '';
        if (t.includes('FBA费用') && el.children.length <= 4) { marker = el; break; }
    }
    if (!marker) {
        // Fallback: tightest container holding all upper markers
        const ms = %s;
        let best = null;
        for (const el of all) {
            const t = el.innerText || '';
            if (ms.every(m => t.includes(m))) {
                if (best === null || t.length < (best.innerText || '').length) best = el;
            }
        }
        return best ? best.innerText : (document.body ? document.body.innerText : '');
    }
    // Climb to the panel root: ancestor containing ASIN + a metric marker
    let node = marker;
    for (let i = 0; i < 10 && node.parentElement; i++) {
        node = node.parentElement;
        const t = node.innerText || '';
        if (t.includes('ASIN') && (t.includes('销售额') || t.includes('近30天销量'))) {
            return t;
        }
    }
    return node ? (node.innerText || '') : '';
}""" % ("[" + ",".join(f'"{m}"' for m in _PANEL_MARKERS) + "]")


class SellerSpriteAdapter(BaseExtensionAdapter):
    name = "seller_sprite"

    def empty_data(self) -> dict:
        return {
            # SellerSprite-only metrics
            "ss_monthly_sales_parent": "",
            "ss_monthly_sales_child": "",
            "ss_monthly_revenue": "",
            "ss_fba_fee": "",
            "ss_gross_margin": "",
            "ss_shipping_days": "",
            "ss_total_traffic": "",
            "ss_organic_traffic": "",
            "ss_ad_traffic": "",
            "ss_recommend_traffic": "",
            "ss_style": "",
            "ss_rating": "",
            # Canonical product keys (fill existing Excel columns when empty)
            "seller_name": "",
            "sif_seller_count": "",
            "bsr": "",
            "main_category": "",
            "subcategory": "",
            "variation_count": "",
            "item_weight": "",
            "product_dimensions": "",
            "package_weight": "",
            "package_dimensions": "",
            "listing_date": "",
        }

    def extract_sync(self, page, asin: str) -> dict:
        """
        Read SellerSprite data from the live Playwright page (sync).

        The caller waits until the overlay has loaded
        (BrowserController.wait_for_seller_sprite); this only reads the DOM.
        """
        result = self.empty_data()
        try:
            panel_text = page.evaluate(_JS_GET_PANEL)
        except Exception as exc:
            logger.debug(f"SellerSprite panel read error for {asin}: {exc}")
            return result

        if not panel_text:
            return result

        # Keep the raw panel text (single-line, truncated) for debugging.
        # Underscore-prefixed so the exporter ignores it.
        result["_ss_panel_text"] = " ⏎ ".join(
            ln.strip() for ln in panel_text.splitlines() if ln.strip()
        )[:600]

        try:
            self._parse_panel(panel_text, result)
        except Exception as exc:
            logger.debug(f"SellerSprite parse error for {asin}: {exc}")
        return result

    # ------------------------------------------------------------------ #
    # Parsing helpers
    # ------------------------------------------------------------------ #

    # label keyword(s) -> (result_key, post-processor or None)
    _LABEL_MAP = [
        (["近30天销量(父体)", "近30天销量（父体）", "月销量(父体)"], "ss_monthly_sales_parent"),
        (["近30天销量(子体)", "近30天销量（子体）", "月销量(子体)"], "ss_monthly_sales_child"),
        (["销售额", "月销售额", "近30天销售额"],                       "ss_monthly_revenue"),
        (["FBA费用", "FBA Fee", "FBA配送费"],                         "ss_fba_fee"),
        (["毛利率", "利润率"],                                        "ss_gross_margin"),
        (["配送时长", "配送天数", "发货时效"],                          "ss_shipping_days"),
        (["全部流量词", "全部流量", "总流量"],                          "ss_total_traffic"),
        (["自然搜索词", "自然流量"],                                   "ss_organic_traffic"),
        (["广告流量词", "广告流量", "广告词"],                          "ss_ad_traffic"),
        (["搜索推荐词", "搜索推荐", "关联推荐"],                         "ss_recommend_traffic"),
        (["变体数", "变体数量"],                                       "variation_count"),
        (["Style", "款式"],                                          "ss_style"),
        (["评分(评分数)", "评分（评分数）"],                            "ss_rating"),
        (["商品重量", "产品重量"],                                     "item_weight"),
        (["商品尺寸", "产品尺寸"],                                     "product_dimensions"),
        (["包装重量", "包裹重量"],                                     "package_weight"),
        (["包装尺寸", "包裹尺寸"],                                     "package_dimensions"),
        (["上架时间", "上架日期"],                                     "listing_date"),
    ]

    def _parse_panel(self, text: str, result: dict) -> None:
        # Normalize: put every known label at the start of its own line so a
        # value never bleeds into the next inline field.
        norm = text
        all_labels = [lbl for labels, _ in self._LABEL_MAP for lbl in labels]
        # Longest labels first so "近30天销量(父体)" wins over "近30天销量".
        for lbl in sorted(all_labels, key=len, reverse=True):
            norm = re.sub(r"\s*" + re.escape(lbl) + r"\s*[:：]", "\n" + lbl + ":", norm)

        for labels, key in self._LABEL_MAP:
            if result.get(key):
                continue
            for lbl in labels:
                m = re.search(r"^" + re.escape(lbl) + r"\s*[:：]\s*(.+)$", norm, re.MULTILINE)
                if m:
                    val = m.group(1).strip()
                    if val:
                        result[key] = self._clean(key, val)
                        break

        # 卖家 appears twice: "卖家: Amazon" (seller) and "... 卖家: 14" (count)
        sellers = re.findall(r"卖家\s*[:：]\s*([^\n]+)", text)
        for s in sellers:
            s = s.strip()
            if re.fullmatch(r"[\d,]+", s):
                result["sif_seller_count"] = s.replace(",", "")
            elif s and not result["seller_name"]:
                # cut off any trailing inline content (e.g. "Amazon  配送:")
                result["seller_name"] = re.split(r"\s{2,}|\t", s)[0].strip()

        # BSR ranks: "#1,401 in Sports & Outdoors" / "#2 in Camping Cots"
        bsr = re.findall(r"#\s*([\d,]+)\s+in\s+([^\n#]+)", text)
        if bsr:
            rank1, cat1 = bsr[0]
            result["bsr"] = f"#{rank1.strip()}"
            result["main_category"] = cat1.strip()
            if len(bsr) > 1:
                rank2, cat2 = bsr[1]
                result["subcategory"] = f"#{rank2.strip()} in {cat2.strip()}"

    @staticmethod
    def _clean(key: str, val: str) -> str:
        if key == "listing_date":
            # "2011-04-19 (5,525天)" -> "2011-04-19"
            m = re.search(r"\d{4}-\d{1,2}-\d{1,2}", val)
            if m:
                return m.group(0)
        if key == "variation_count":
            m = re.search(r"\d+", val)
            if m:
                return m.group(0)
        return val

    # Keep async stub so the class still satisfies BaseExtensionAdapter
    async def extract(self, page, asin: str) -> dict:
        return self.empty_data()

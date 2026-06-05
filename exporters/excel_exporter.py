"""
Excel exporter using openpyxl.

Layout (left to right):
  基本信息 Basic Info  |  成本项 Costs  |  收入项 Revenue  |  利润计算 Profit

The sheet has two header rows:
  Row 1 = group bands (merged, color-coded)
  Row 2 = field headers
  Row 3+ = data

Cost / revenue items are ALWAYS listed even when we cannot scrape them, so
the user can fill the blanks in later. Profit and profit margin are live
Excel formulas, so editing any cost/revenue cell recalculates automatically.
"""
import os
import re
from datetime import datetime
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

# Each column: (key, header, kind, group)
#   kind: "text"  -> raw string
#         "money" -> numeric value parsed from strings like "$54.99"
#         "formula:<name>" -> Excel formula generated per row
#   group: used for the merged band in row 1
G_BASIC   = "基本信息 Basic Info"
G_COST    = "成本项 Costs"
G_REVENUE = "收入项 Revenue"
G_PROFIT  = "利润计算 Profit"
G_AI      = "AI评价 AI Review"

COLUMNS = [
    # ---------------- 基本信息 Basic Info ----------------
    ("asin",                     "ASIN",                          "text",  G_BASIC),
    ("title",                    "产品标题(Title)",                "text",  G_BASIC),
    ("brand",                    "品牌(Brand)",                    "text",  G_BASIC),
    ("seller_name",              "卖家(Seller)",                   "text",  G_BASIC),
    ("sif_seller_count",         "卖家数量(Seller Count)",          "text",  G_BASIC),
    ("bsr",                      "BSR排名(BSR)",                   "text",  G_BASIC),
    ("main_category",            "主类目(Main Category)",          "text",  G_BASIC),
    ("subcategory",              "子类目(Subcategory)",            "text",  G_BASIC),
    ("rating",                   "评分(Rating)",                   "text",  G_BASIC),
    ("review_count",             "评论数(Reviews)",                "text",  G_BASIC),
    ("ss_rating",                "评分_评分数(Rating/Count)",       "text",  G_BASIC),
    ("ss_monthly_sales_parent",  "月销量-父体(Sales Parent)",       "text",  G_BASIC),
    ("ss_monthly_sales_child",   "月销量-子体(Sales Child)",        "text",  G_BASIC),
    ("listing_date",             "上架时间(Launch Date)",          "text",  G_BASIC),
    ("variation_count",          "变体数量(Variations)",            "text",  G_BASIC),
    ("ss_style",                 "款式(Style)",                    "text",  G_BASIC),
    ("item_weight",              "商品重量(Item Weight)",           "text",  G_BASIC),
    ("product_dimensions",       "商品尺寸(Product Dimensions)",    "text",  G_BASIC),
    ("package_weight",           "包裹重量(Package Weight)",        "text",  G_BASIC),
    ("package_dimensions",       "包裹尺寸(Package Dimensions)",    "text",  G_BASIC),
    ("fulfillment",              "配送方式(Fulfillment)",           "text",  G_BASIC),
    ("ss_shipping_days",         "配送时长(Shipping Days)",         "text",  G_BASIC),
    ("coupon_discount",          "优惠券(Coupon)",                 "text",  G_BASIC),
    ("ss_total_traffic",         "全部流量词(Total Traffic)",       "text",  G_BASIC),
    ("ss_organic_traffic",       "自然搜索词(Organic Traffic)",     "text",  G_BASIC),
    ("ss_ad_traffic",            "广告流量词(Ad Traffic)",          "text",  G_BASIC),
    ("ss_recommend_traffic",     "搜索推荐词(Recommend Traffic)",   "text",  G_BASIC),
    ("bullet_points",            "卖点(Bullet Points)",            "text",  G_BASIC),
    ("product_description",      "产品描述(Description)",          "text",  G_BASIC),
    ("main_image_url",           "主图URL(Main Image)",            "text",  G_BASIC),
    ("all_image_urls",           "全部图片URL(All Images)",         "text",  G_BASIC),
    ("product_url",              "产品URL(Product URL)",           "text",  G_BASIC),
    ("page_number",              "页码(Page)",                     "text",  G_BASIC),
    ("collection_timestamp",     "采集时间(Timestamp)",            "text",  G_BASIC),

    # ---------------- 成本项 Costs (per unit) ----------------
    # 金额已知类：填金额 → 公式算占比
    ("product_cost",             "采购成本(Product Cost)",          "money",                      G_COST),
    ("product_cost_pct",         "采购占比%",                       "formula:pct:product_cost",   G_COST),
    ("freight_cost",             "头程运费(Freight)",               "money",                      G_COST),
    ("freight_cost_pct",         "头程占比%",                       "formula:pct:freight_cost",   G_COST),
    ("ss_fba_fee",               "FBA配送费(FBA Fee)",              "money",                      G_COST),
    ("ss_fba_fee_pct",           "FBA占比%",                        "formula:pct:ss_fba_fee",     G_COST),
    ("storage_fee",              "仓储费(Storage Fee)",            "money",                      G_COST),
    ("storage_fee_pct",          "仓储占比%",                       "formula:pct:storage_fee",    G_COST),
    ("other_cost",               "其他成本(Other Cost)",           "money",                      G_COST),
    ("other_cost_pct",           "其他占比%",                       "formula:pct:other_cost",     G_COST),
    # 占比已知类：填占比% → 公式算金额
    ("referral_fee_pct",         "平台佣金占比%(填小数如0.15)",      "pct_input:0.15",             G_COST),
    ("referral_fee",             "平台佣金(Referral Fee)",          "formula:from_pct:referral_fee_pct", G_COST),
    ("ad_cost_pct",              "广告费占比%(填小数如0.10)",        "pct_input:0",                G_COST),
    ("ad_cost",                  "广告费(Ad Cost)",                "formula:from_pct:ad_cost_pct", G_COST),
    ("return_cost_pct",          "退货占比%(填小数如0.05)",          "pct_input:0",                G_COST),
    ("return_cost",              "退货成本(Returns)",              "formula:from_pct:return_cost_pct", G_COST),
    # 汇总
    ("total_cost",               "总成本(Total Cost)",             "formula:total_cost",         G_COST),
    ("total_cost_pct",           "总成本占比%",                     "formula:pct:total_cost",     G_COST),

    # ---------------- 收入项 Revenue (per unit) ----------------
    ("price",                    "售价(Selling Price)",            "money", G_REVENUE),
    ("other_revenue",            "其他收入(Other Revenue)",         "money", G_REVENUE),
    ("total_revenue",            "总收入(Total Revenue)",           "formula:total_revenue", G_REVENUE),
    ("ss_monthly_revenue",       "月销售额-参考(Monthly Rev. ref)", "text",  G_REVENUE),

    # ---------------- 利润计算 Profit ----------------
    ("profit",                   "单件利润(Profit)",                "formula:profit",        G_PROFIT),
    ("profit_margin",            "利润率(Profit Margin)",           "formula:profit_margin", G_PROFIT),
    ("ss_gross_margin",          "毛利率-卖家精灵(SS Margin ref)",  "text",  G_PROFIT),

    # ---------------- AI评价 AI Review ----------------
    ("ai_evaluation",            "AI选品评价(AI Evaluation)",       "text",  G_AI),
]

# Styling
HEADER_FILL = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
HEADER_FONT = Font(bold=True, color="FFFFFF", size=11)
GROUP_FONT  = Font(bold=True, color="FFFFFF", size=12)
GROUP_FILLS = {
    G_BASIC:   PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid"),
    G_COST:    PatternFill(start_color="C0504D", end_color="C0504D", fill_type="solid"),
    G_REVENUE: PatternFill(start_color="4F8A4F", end_color="4F8A4F", fill_type="solid"),
    G_PROFIT:  PatternFill(start_color="E0A526", end_color="E0A526", fill_type="solid"),
    G_AI:      PatternFill(start_color="6F42C1", end_color="6F42C1", fill_type="solid"),
}
ROW_FILL_A  = PatternFill(start_color="EBF3FB", end_color="EBF3FB", fill_type="solid")
ROW_FILL_B  = PatternFill(start_color="FFFFFF", end_color="FFFFFF", fill_type="solid")
THIN = Side(style="thin", color="D0D0D0")
CELL_BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
MAX_COL_WIDTH = 50
MIN_COL_WIDTH = 10
MONEY_FMT = "#,##0.00"
PCT_FMT = "0.0%"
WRAP_KEYS = {"bullet_points", "product_description", "ai_evaluation"}


def _parse_money(value) -> float | None:
    """Extract a float from strings like '$54.99', '1,234.5'. Returns None if none."""
    if value is None:
        return None
    s = str(value).replace(",", "")
    m = re.search(r"-?\d+(\.\d+)?", s)
    return float(m.group(0)) if m else None


def _col_letters() -> dict:
    """Map each column key to its Excel column letter."""
    return {key: get_column_letter(i) for i, (key, *_rest) in enumerate(COLUMNS, start=1)}


def export(products: list, output_path: str) -> str:
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    wb = Workbook()
    ws = wb.active
    ws.title = "Amazon数据采集"

    letters = _col_letters()

    # Cost item keys that contribute real monetary values to the total.
    # Includes: money cols + from_pct formula cols (referral/ad/return).
    # Excludes: pct_input cols, formula:pct cols, and total_cost itself.
    cost_value_keys = [
        k for k, _, kind, grp in COLUMNS
        if grp == G_COST
        and kind not in ("formula:total_cost", "pct_input:0", "pct_input:0.15")
        and not kind.startswith("formula:pct")
        and not kind.startswith("pct_input")
    ]

    # ---------- Row 1: group bands ----------
    # Find contiguous runs of the same group and merge them.
    col = 1
    n = len(COLUMNS)
    while col <= n:
        grp = COLUMNS[col - 1][3]
        start = col
        while col <= n and COLUMNS[col - 1][3] == grp:
            col += 1
        end = col - 1
        c = ws.cell(row=1, column=start, value=grp)
        c.font = GROUP_FONT
        c.fill = GROUP_FILLS.get(grp, HEADER_FILL)
        c.alignment = Alignment(horizontal="center", vertical="center")
        if end > start:
            ws.merge_cells(start_row=1, start_column=start, end_row=1, end_column=end)

    # ---------- Row 2: field headers ----------
    for col_idx, (_key, header, _kind, _grp) in enumerate(COLUMNS, start=1):
        cell = ws.cell(row=2, column=col_idx, value=header)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = CELL_BORDER

    ws.row_dimensions[1].height = 22
    ws.row_dimensions[2].height = 30

    # ---------- Data rows (start at row 3) ----------
    for offset, product in enumerate(products):
        row_idx = offset + 3
        fill = ROW_FILL_A if offset % 2 == 0 else ROW_FILL_B
        for col_idx, (key, _header, kind, _grp) in enumerate(COLUMNS, start=1):
            cell = ws.cell(row=row_idx, column=col_idx)

            if kind == "money":
                cell.value = _parse_money(product.get(key))
                cell.number_format = MONEY_FMT
            elif kind.startswith("pct_input:"):
                # User-editable percentage cell. Pre-fill with default decimal value.
                default_str = kind.split(":", 1)[1]
                default_val = float(default_str) if default_str else None
                cell.value = default_val if default_val else None
                cell.number_format = PCT_FMT
            elif kind.startswith("formula:"):
                name = kind.split(":", 1)[1]
                cell.value = _formula(name, row_idx, letters, cost_value_keys)
                is_pct = (name in ("profit_margin",) or name.startswith("pct:"))
                cell.number_format = PCT_FMT if is_pct else MONEY_FMT
            else:  # text
                cell.value = str(product.get(key, "") or "")

            cell.fill = fill
            cell.border = CELL_BORDER
            wrap = key in WRAP_KEYS
            cell.alignment = Alignment(vertical="top" if wrap else "center", wrap_text=wrap)

    # ---------- Column widths ----------
    last_row = ws.max_row
    for col_idx, (_key, header, _kind, _grp) in enumerate(COLUMNS, start=1):
        col_letter = get_column_letter(col_idx)
        max_len = len(header)
        for r in range(3, last_row + 1):
            v = ws.cell(row=r, column=col_idx).value
            max_len = max(max_len, min(len(str(v if v is not None else "")), MAX_COL_WIDTH))
        ws.column_dimensions[col_letter].width = min(max(max_len + 2, MIN_COL_WIDTH), MAX_COL_WIDTH)

    # Freeze the two header rows
    ws.freeze_panes = "A3"

    wb.save(output_path)
    return output_path


def _formula(name: str, row: int, letters: dict, cost_value_keys: list) -> str:
    """Build the Excel formula string for a computed column on a given row."""
    rev    = f"{letters['total_revenue']}{row}"
    cost   = f"{letters['total_cost']}{row}"
    profit = f"{letters['profit']}{row}"
    price  = f"{letters['price']}{row}"
    other_rev = f"{letters['other_revenue']}{row}"

    # from_pct:<pct_key> — money = price × pct_input cell
    if name.startswith("from_pct:"):
        pct_key = name[9:]
        pct_cell = f"{letters[pct_key]}{row}"
        return f'=IF({pct_cell}="","",{price}*{pct_cell})'

    if name == "referral_fee":
        # Legacy fallback — column now driven by referral_fee_pct input
        return f"={price}*0.15"

    if name == "total_cost":
        # Sum only the real cost cells (money + referral_fee), skip pct columns
        parts = "+".join(f"{letters[k]}{row}" for k in cost_value_keys)
        return f"={parts}"

    if name == "total_revenue":
        return f"=SUM({price},{other_rev})"

    if name == "profit":
        return f"={rev}-{cost}"

    if name == "profit_margin":
        return f'=IF({rev}=0,"",{profit}/{rev})'

    # pct:<cost_key> — percentage of selling price
    if name.startswith("pct:"):
        cost_key = name[4:]
        cost_cell = f"{letters[cost_key]}{row}"
        return f'=IF({price}=0,"",{cost_cell}/{price})'

    return ""


def generate_output_filename(keyword_or_url: str, output_dir: str) -> str:
    """Generate a timestamped output filename for the export."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = "".join(
        c if c.isalnum() or c in " _-" else "_"
        for c in keyword_or_url[:40]
    ).strip().replace(" ", "_")
    filename = f"amazon_{safe_name}_{timestamp}.xlsx"
    return os.path.join(output_dir, filename)

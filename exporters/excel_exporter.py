"""
Excel exporter using openpyxl.
Exports collected Amazon product data with styled headers and alternating row colors.
"""
import os
from datetime import datetime
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

# Column definitions: (field_key, display_header)
# field_key must match keys in the product dict.
# display_header is the column header shown in the Excel file.
COLUMNS = [
    ("asin",                     "ASIN"),
    ("title",                    "产品标题(Title)"),
    ("brand",                    "品牌(Brand)"),
    ("price",                    "价格(Price)"),
    ("rating",                   "评分(Rating)"),
    ("review_count",             "评论数(Reviews)"),
    ("coupon_discount",          "优惠券(Coupon)"),
    ("fulfillment",              "配送方式(Fulfillment)"),
    ("seller_name",              "卖家(Seller)"),
    ("sif_seller_count",         "卖家数量(Seller Count)"),
    ("bsr",                      "BSR排名(BSR)"),
    ("main_category",            "主类目(Main Category)"),
    ("subcategory",              "子类目(Subcategory)"),
    ("listing_date",             "上架时间(Launch Date)"),
    ("variation_count",          "变体数量(Variations)"),
    # SellerSprite extension fields
    ("ss_monthly_sales_parent",  "月销量-父体(Monthly Sales Parent)"),
    ("ss_monthly_sales_child",   "月销量-子体(Monthly Sales Child)"),
    ("ss_monthly_revenue",       "月销售额(Monthly Revenue)"),
    ("ss_fba_fee",               "FBA费用(FBA Fee)"),
    ("ss_gross_margin",          "毛利率(Gross Margin)"),
    ("ss_shipping_days",         "配送时长(Shipping Days)"),
    ("ss_total_traffic",         "全部流量(Total Traffic)"),
    ("ss_organic_traffic",       "自然搜索词(Organic Traffic)"),
    ("ss_ad_traffic",            "广告流量(Ad Traffic)"),
    ("ss_recommend_traffic",     "搜索推荐(Recommend Traffic)"),
    # Physical product specs (from Amazon detail page)
    ("item_weight",              "商品重量(Item Weight)"),
    ("product_dimensions",       "商品尺寸(Product Dimensions)"),
    ("package_weight",           "包裹重量(Package Weight)"),
    ("package_dimensions",       "包裹尺寸(Package Dimensions)"),
    # Detail page content
    ("bullet_points",            "卖点(Bullet Points)"),
    ("product_description",      "产品描述(Description)"),
    ("main_image_url",           "主图URL(Main Image)"),
    ("all_image_urls",           "全部图片URL(All Images)"),
    ("product_url",              "产品URL(Product URL)"),
    ("page_number",              "页码(Page)"),
    ("collection_timestamp",     "采集时间(Timestamp)"),
    ("source_url",               "来源URL(Source URL)"),
]

# Styling constants
HEADER_FILL = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
HEADER_FONT = Font(bold=True, color="FFFFFF", size=11)
ROW_FILL_A  = PatternFill(start_color="EBF3FB", end_color="EBF3FB", fill_type="solid")
ROW_FILL_B  = PatternFill(start_color="FFFFFF", end_color="FFFFFF", fill_type="solid")
MAX_COL_WIDTH = 50
MIN_COL_WIDTH = 10


def export(products: list, output_path: str) -> str:
    """
    Export a list of product dicts to an Excel file at output_path.

    Args:
        products: List of product dicts. Missing keys are treated as empty string.
        output_path: Absolute path for the output .xlsx file.

    Returns:
        The output_path (for convenience).
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    wb = Workbook()
    ws = wb.active
    ws.title = "Amazon数据采集"

    # Write header row
    headers = [col[1] for col in COLUMNS]
    ws.append(headers)
    for col_idx, _ in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col_idx)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=False)

    ws.row_dimensions[1].height = 22

    # Write data rows
    # Columns that contain multi-line text and should wrap
    WRAP_KEYS = {"bullet_points", "product_description"}

    for row_idx, product in enumerate(products, start=2):
        row_data = [str(product.get(key, "") or "") for key, _ in COLUMNS]
        ws.append(row_data)
        fill = ROW_FILL_A if row_idx % 2 == 0 else ROW_FILL_B
        for col_idx, (key, _) in enumerate(COLUMNS, start=1):
            cell = ws.cell(row=row_idx, column=col_idx)
            cell.fill = fill
            wrap = key in WRAP_KEYS
            cell.alignment = Alignment(vertical="top" if wrap else "center", wrap_text=wrap)

    # Auto-size columns based on content
    for col_idx, (_, header) in enumerate(COLUMNS, start=1):
        col_letter = get_column_letter(col_idx)
        # Measure max content width in this column
        max_len = len(header)
        for row_idx in range(2, ws.max_row + 1):
            cell_value = str(ws.cell(row=row_idx, column=col_idx).value or "")
            # Limit scan length to avoid slow processing on long URLs
            max_len = max(max_len, min(len(cell_value), MAX_COL_WIDTH))
        # Add a little padding and clamp
        width = min(max(max_len + 2, MIN_COL_WIDTH), MAX_COL_WIDTH)
        ws.column_dimensions[col_letter].width = width

    # Freeze header row
    ws.freeze_panes = "A2"

    wb.save(output_path)
    return output_path


def generate_output_filename(keyword_or_url: str, output_dir: str) -> str:
    """Generate a timestamped output filename for the export."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    # Sanitize keyword for use in filename
    safe_name = "".join(
        c if c.isalnum() or c in " _-" else "_"
        for c in keyword_or_url[:40]
    ).strip().replace(" ", "_")
    filename = f"amazon_{safe_name}_{timestamp}.xlsx"
    return os.path.join(output_dir, filename)

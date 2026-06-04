"""
Amazon search results and product detail page parser.
Uses BeautifulSoup for HTML parsing.
"""
import re
import urllib.parse
from datetime import datetime
from bs4 import BeautifulSoup
import logging

logger = logging.getLogger(__name__)


def parse_search_results(html: str, page_url: str, page_num: int) -> list:
    """
    Parse an Amazon search/category results page HTML.

    Returns a list of product dicts with standardized fields.
    Fields are empty string when not found.
    """
    soup = BeautifulSoup(html, "lxml")
    products = []
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

    # Determine marketplace base URL from page_url
    parsed = urllib.parse.urlparse(page_url)
    marketplace_base = f"{parsed.scheme}://{parsed.netloc}"

    # Amazon search result cards: div[data-component-type="s-search-result"]
    result_items = soup.select('div[data-component-type="s-search-result"]')
    logger.debug(f"Found {len(result_items)} result items on page {page_num}")

    for item in result_items:
        asin = item.get("data-asin", "").strip()
        if not asin:
            continue

        product = {
            "asin": asin,
            "title": "",
            "brand": "",
            "price": "",
            "rating": "",
            "review_count": "",
            "main_image_url": "",
            "product_url": "",
            "coupon_discount": "",
            "fulfillment": "",
            "seller_name": "",
            "bsr": "",
            "main_category": "",
            "subcategory": "",
            "page_number": page_num,
            "collection_timestamp": timestamp,
            "source_url": page_url,
        }

        # Title — try multiple common selectors
        for sel in (
            "h2 .a-size-base-plus.a-color-base",
            "h2 .a-size-medium.a-color-base.a-text-normal",
            "h2 .a-size-base.a-color-base",
            "h2 span",
        ):
            el = item.select_one(sel)
            if el and el.get_text(strip=True):
                product["title"] = el.get_text(strip=True)
                break

        # Price
        price_el = item.select_one(".a-price .a-offscreen")
        if price_el:
            product["price"] = price_el.get_text(strip=True)

        # Rating (e.g. "4.5 out of 5 stars")
        for rating_sel in (
            ".a-icon-star-small .a-icon-alt",
            '[data-cy="reviews-ratings-slot"] .a-icon-alt',
            ".a-icon-star .a-icon-alt",
            "[aria-label*='stars']",
        ):
            rating_el = item.select_one(rating_sel)
            if rating_el:
                text = rating_el.get_text(strip=True)
                if text:
                    product["rating"] = text
                    break
            # Try aria-label attribute on star icons
            rating_el = item.select_one(rating_sel.split(" ")[0])
            if rating_el:
                aria = rating_el.get("aria-label", "")
                if "star" in aria.lower() or "out of" in aria.lower():
                    product["rating"] = aria
                    break

        # Review count
        for review_sel in (
            ".a-size-base.s-underline-text",
            '[data-cy="reviews-ratings-slot"] .a-size-base',
            ".a-link-normal .a-size-base",
        ):
            review_el = item.select_one(review_sel)
            if review_el:
                text = review_el.get_text(strip=True)
                # Must look like a number (possibly with commas)
                if re.match(r"^[\d,]+$", text.replace(",", "").replace(".", "")):
                    product["review_count"] = text
                    break

        # Main image
        img_el = item.select_one("img.s-image")
        if img_el:
            product["main_image_url"] = img_el.get("src", "")

        # Product URL
        link_el = item.select_one("h2 a[href]")
        if link_el:
            href = link_el.get("href", "")
            if href.startswith("http"):
                product["product_url"] = href
            else:
                product["product_url"] = marketplace_base + href

        # Coupon
        coupon_el = item.select_one(".s-coupon-unclipped") or item.select_one("[data-csa-c-type='coupon']")
        if coupon_el:
            product["coupon_discount"] = coupon_el.get_text(strip=True)

        # Fulfillment — look for FBA/Amazon shipping signals
        item_text = item.get_text(" ", strip=True).lower()
        if any(phrase in item_text for phrase in ("fulfilled by amazon", "ships from amazon", "amazon.com")):
            product["fulfillment"] = "FBA"
        elif "fulfilled by" in item_text:
            product["fulfillment"] = "FBM"

        # Seller name (sometimes visible in search results)
        for seller_sel in (".a-size-small.s-underline-text", ".a-color-secondary .a-size-small"):
            seller_el = item.select_one(seller_sel)
            if seller_el:
                text = seller_el.get_text(strip=True)
                if text and len(text) < 80:
                    product["seller_name"] = text
                    break

        products.append(product)

    return products


def parse_product_detail(html: str, asin: str) -> dict:
    """
    Parse a product detail page and return a dict of enriched fields.
    Merges with existing product data — fields not found remain empty string.
    """
    soup = BeautifulSoup(html, "lxml")

    result = {
        "asin": asin,
        "title": "",
        "brand": "",
        "price": "",
        "rating": "",
        "review_count": "",
        "main_image_url": "",
        "bsr": "",
        "main_category": "",
        "subcategory": "",
        "listing_date": "",
        "fulfillment": "",
        "seller_name": "",
        "variation_count": "",
    }

    # Title
    title_el = soup.select_one("#productTitle")
    if title_el:
        result["title"] = title_el.get_text(strip=True)

    # Brand
    brand_el = soup.select_one("#bylineInfo")
    if brand_el:
        result["brand"] = brand_el.get_text(strip=True).replace("Brand: ", "").replace("Visit the ", "").strip()

    # Price — try multiple locations
    for price_sel in (
        "#corePriceDisplay_desktop_feature_div .a-price .a-offscreen",
        ".a-price.a-text-price.a-size-medium .a-offscreen",
        "#priceblock_ourprice",
        "#priceblock_dealprice",
        ".priceToPay .a-offscreen",
        "#price_inside_buybox",
    ):
        price_el = soup.select_one(price_sel)
        if price_el:
            text = price_el.get_text(strip=True)
            if text:
                result["price"] = text
                break

    # Rating
    rating_el = soup.select_one("#acrPopover .a-icon-alt")
    if not rating_el:
        rating_el = soup.select_one("[data-hook='rating-out-of-text']")
    if rating_el:
        result["rating"] = rating_el.get_text(strip=True)

    # Review count
    review_el = soup.select_one("#acrCustomerReviewText")
    if review_el:
        result["review_count"] = review_el.get_text(strip=True)

    # Main image
    for img_sel in (
        "#landingImage",
        "#imgTagWrapperId img",
        "#main-image",
        "#imageBlock img",
    ):
        img_el = soup.select_one(img_sel)
        if img_el:
            src = img_el.get("src") or img_el.get("data-a-dynamic-image", "")
            if src and src.startswith("http"):
                result["main_image_url"] = src
                break

    # BSR and category — parse from detail bullets
    bsr_text = _extract_bsr(soup)
    if bsr_text:
        result["bsr"] = bsr_text["rank"]
        result["main_category"] = bsr_text.get("main_category", "")
        result["subcategory"] = bsr_text.get("subcategory", "")

    # Date First Available
    listing_date = _extract_detail_bullet(soup, "Date First Available")
    if listing_date:
        result["listing_date"] = listing_date

    # Fulfillment
    page_text = soup.get_text(" ", strip=True).lower()
    if "fulfilled by amazon" in page_text or "ships from amazon.com" in page_text:
        result["fulfillment"] = "FBA"
    elif "fulfilled by" in page_text:
        result["fulfillment"] = "FBM"

    # Seller name
    for seller_sel in (
        "#sellerProfileTriggerId",
        "#merchantInfoFeature_feature_div .offer-display-feature-text",
        "#merchant-info a",
    ):
        seller_el = soup.select_one(seller_sel)
        if seller_el:
            text = seller_el.get_text(strip=True)
            if text:
                result["seller_name"] = text
                break

    # Variation count — count variation option elements
    variation_total = 0
    for var_sel in (
        "#variation_color_name li",
        "#variation_size_name li",
        "#variation_style_name li",
        "#variation_flavor_name li",
        "#variation_package_quantity li",
        "#variation_material_type li",
        "[id^='variation_'] li",
    ):
        variation_els = soup.select(var_sel)
        if variation_els:
            variation_total += len(variation_els)
    if variation_total:
        result["variation_count"] = str(variation_total)

    # Product dimensions and weight from detail bullets / tech specs
    for label in ("Item Dimensions LxWxH", "Item Dimensions", "Product Dimensions"):
        val = _extract_detail_bullet(soup, label)
        if val:
            result["product_dimensions"] = val
            break

    for label in ("Item Weight", "Product Weight"):
        val = _extract_detail_bullet(soup, label)
        if val:
            result["item_weight"] = val
            break

    for label in ("Package Dimensions",):
        val = _extract_detail_bullet(soup, label)
        if val:
            result["package_dimensions"] = val
            break

    for label in ("Package Weight",):
        val = _extract_detail_bullet(soup, label)
        if val:
            result["package_weight"] = val
            break

    return result


def _extract_bsr(soup: BeautifulSoup) -> dict:
    """Extract Best Sellers Rank information from a product detail page."""
    # Try the dedicated BSR element
    bsr_el = soup.select_one("#SalesRank")
    if not bsr_el:
        # Try detail bullets
        for container_sel in (
            "#detailBulletsWrapper_feature_div",
            "#productDetails_detailBullets_sections1",
            "#prodDetails",
        ):
            container = soup.select_one(container_sel)
            if container:
                text = container.get_text(" ", strip=True)
                if "Best Sellers Rank" in text or "Amazon Best Sellers Rank" in text:
                    bsr_el = container
                    break

    if not bsr_el:
        return {}

    text = bsr_el.get_text(" ", strip=True)

    # Parse rank number: e.g. "#1,234 in Tools & Home Improvement"
    rank_match = re.search(r"#([\d,]+)\s+in\s+([^(#\n]+)", text)
    if not rank_match:
        rank_match = re.search(r"([\d,]+)\s+in\s+([^(#\n]+)", text)

    if rank_match:
        rank_str = "#" + rank_match.group(1).strip()
        category_str = rank_match.group(2).strip().rstrip("(").strip()

        # Try to find a subcategory rank
        sub_match = re.search(r"#([\d,]+)\s+in\s+([^(#\n]+)\s*\(", text)
        subcategory = ""
        if sub_match and sub_match.group(2).strip() != category_str:
            subcategory = sub_match.group(2).strip()

        return {
            "rank": rank_str,
            "main_category": category_str,
            "subcategory": subcategory,
        }

    return {}


def _extract_detail_bullet(soup: BeautifulSoup, label: str) -> str:
    """Extract a value from the detail bullets table by label text."""
    for container_sel in (
        "#detailBulletsWrapper_feature_div",
        "#productDetails_detailBullets_sections1",
        "#prodDetails",
        "#detailBullets_feature_div",
    ):
        container = soup.select_one(container_sel)
        if not container:
            continue

        # Table format
        for row in container.select("tr"):
            th = row.select_one("th")
            td = row.select_one("td")
            if th and td and label.lower() in th.get_text(strip=True).lower():
                return td.get_text(strip=True)

        # List format (detail bullets)
        for li in container.select("li"):
            text = li.get_text(" ", strip=True)
            if label.lower() in text.lower():
                parts = text.split(":", 1)
                if len(parts) == 2:
                    return parts[1].strip()

    return ""


def build_search_url(keyword: str, marketplace_url: str, page: int = 1) -> str:
    """Build an Amazon search URL for the given keyword and page number."""
    encoded = urllib.parse.quote(keyword)
    if page > 1:
        return f"{marketplace_url}/s?k={encoded}&page={page}"
    return f"{marketplace_url}/s?k={encoded}"


def is_category_url(url: str) -> bool:
    """Return True if the URL looks like an Amazon category/browse URL."""
    parsed = urllib.parse.urlparse(url)
    path = parsed.path.lower()
    query = parsed.query.lower()
    return (
        "/b?" in url
        or path.startswith("/b/")
        or "node=" in query
        or re.search(r"/[a-z0-9-]+/b/ref=", url) is not None
    )


def build_paginated_url(url: str, page: int) -> str:
    """
    Return the URL for a specific page number.
    Works for both search URLs (has &page=) and category URLs.
    """
    if page <= 1:
        return url

    parsed = urllib.parse.urlparse(url)
    params = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    params["page"] = [str(page)]
    new_query = urllib.parse.urlencode(params, doseq=True)
    return urllib.parse.urlunparse(parsed._replace(query=new_query))

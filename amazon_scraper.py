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

        # Product URL — try several link locations, then fall back to ASIN
        for link_sel in (
            "h2 a[href]",
            "a.a-link-normal.s-no-outline[href]",
            "a.a-link-normal[href*='/dp/']",
            ".a-link-normal[href*='/dp/']",
        ):
            link_el = item.select_one(link_sel)
            if link_el:
                href = link_el.get("href", "")
                if href:
                    product["product_url"] = href if href.startswith("http") else marketplace_base + href
                    break
        # Robust fallback: build the canonical product URL straight from the ASIN
        if not product["product_url"] and asin:
            product["product_url"] = f"{marketplace_base}/dp/{asin}"

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
        "all_image_urls": "",
        "bullet_points": "",
        "product_description": "",
        "bsr": "",
        "main_category": "",
        "subcategory": "",
        "listing_date": "",
        "fulfillment": "",
        "seller_name": "",
        "variation_count": "",
        "item_weight": "",
        "product_dimensions": "",
        "package_weight": "",
        "package_dimensions": "",
        "customers_say_summary": "",
        "customers_say_topics": "",
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

    # Main image + all gallery images
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

    # All gallery images — extract from the JSON image data Amazon embeds in the page
    import re as _re, json as _json
    all_images = []
    # Amazon stores image URLs in a JS variable: 'colorImages': { 'initial': [{...}] }
    img_script_match = _re.search(
        r"'colorImages'\s*:\s*\{\s*'initial'\s*:\s*(\[.*?\])\s*\}",
        str(soup), _re.DOTALL
    )
    if img_script_match:
        try:
            img_list = _json.loads(img_script_match.group(1))
            for item in img_list:
                for key in ("hiRes", "large", "main"):
                    url = item.get(key)
                    if url and url.startswith("http") and url not in all_images:
                        all_images.append(url)
                        break
        except Exception:
            pass
    # Fallback: thumbnail strip
    if not all_images:
        for thumb in soup.select("#altImages img, #imageBlock_feature_div img"):
            src = thumb.get("src", "")
            # Convert thumbnail URL to full-size by removing size suffix
            src = _re.sub(r"\._[A-Z]{2}\d+_\.", ".", src)
            if src.startswith("http") and src not in all_images:
                all_images.append(src)
    if all_images:
        result["all_image_urls"] = " | ".join(all_images[:10])  # max 10 images
    elif result["main_image_url"]:
        result["all_image_urls"] = result["main_image_url"]

    # Bullet points (卖点)
    bullets = []
    for bp_sel in (
        "#feature-bullets ul li span.a-list-item",
        "#feature-bullets .a-unordered-list li",
        "#productFactsDesktopExpander .a-list-item",
    ):
        items = soup.select(bp_sel)
        if items:
            for li in items:
                text = li.get_text(strip=True)
                if text and len(text) > 5:
                    bullets.append(text)
            break
    if bullets:
        result["bullet_points"] = "\n".join(bullets)

    # Product description (产品描述)
    for desc_sel in (
        "#productDescription p",
        "#productDescription",
        "#aplus p",
        "#aplus .aplus-v2",
        "[data-feature-name='bookDescription'] p",
    ):
        desc_el = soup.select_one(desc_sel)
        if desc_el:
            text = desc_el.get_text(" ", strip=True)
            if len(text) > 20:
                result["product_description"] = text[:2000]  # cap at 2000 chars
                break

    # BSR and category — parse from detail bullets
    bsr_text = _extract_bsr(soup)
    if bsr_text:
        result["bsr"] = bsr_text["rank"]
        result["main_category"] = bsr_text.get("main_category", "")
        result["subcategory"] = bsr_text.get("subcategory", "")

    # Date First Available — try multiple label variants Amazon uses
    for date_label in (
        "Date First Available",
        "Date first available",
        "Initially available at Amazon",
    ):
        listing_date = _extract_detail_bullet(soup, date_label)
        if listing_date:
            result["listing_date"] = listing_date
            break
    # Also try the product information table (newer Amazon layout)
    if not result["listing_date"]:
        for row in soup.select("#productDetails_techSpec_section_1 tr, "
                               "#productDetails_detailBullets_sections1 tr, "
                               ".prodDetTable tr"):
            th = row.select_one("th")
            td = row.select_one("td")
            if th and td and "first available" in th.get_text(strip=True).lower():
                result["listing_date"] = td.get_text(strip=True)
                break

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

    # "Customers say" — AI-generated summary + topic tags
    # Try every known selector variant Amazon has used; all checked before fallbacks.
    _CS_SUMMARY_SELECTORS = [
        "[data-hook='cr-insights-widget-aspects'] p",
        "#cr-dp-summarization-insights-content p",
        "#cr-summarization-insights-content p",
        ".cr-insight-text-wrapper p",
        "[data-hook='cr-summarization-attributes-list'] ~ p",
        ".a-section.cr-lighthouse-terms + p",
        # 2024+ variants
        "[data-hook='cr-insights-content'] p",
        ".cr-insights-widget-content p",
        "#cr-dp-customer-insights p",
        "[id^='cr-dp-summarization'] p",
        "[class*='cr-insight'] p",
        "[class*='cr-lighthouse'] p",
    ]
    cs_summary_el = None
    for _s in _CS_SUMMARY_SELECTORS:
        cs_summary_el = soup.select_one(_s)
        if cs_summary_el:
            break

    # Broader fallback: find the widget container, then grab first <p> inside it
    if not cs_summary_el:
        for sel in (
            "[data-hook='cr-insights-widget-aspects']",
            "#cr-dp-summarization-insights-content",
            "#cr-summarization-insights-content",
            ".cr-lighthouse-terms",
            "[data-hook='cr-insights-content']",
            "[id^='cr-dp-summarization']",
        ):
            widget = soup.select_one(sel)
            if widget:
                cs_summary_el = widget.find("p")
                if not cs_summary_el:
                    # try parent one level up
                    parent = widget.find_parent("div")
                    if parent:
                        cs_summary_el = parent.find("p")
                break

    # Text-search fallback: find a heading whose text IS "Customers say" and
    # grab the sibling/following paragraph — robust against class-name churn.
    if not cs_summary_el:
        for heading in soup.find_all(["h2", "h3", "h4", "span", "div"]):
            txt = heading.get_text(strip=True)
            if txt in ("Customers say", "Customers Say"):
                # Walk forward siblings until we find a <p>
                for sib in heading.find_next_siblings():
                    if sib.name == "p":
                        cs_summary_el = sib
                        break
                    p = sib.find("p") if hasattr(sib, "find") else None
                    if p:
                        cs_summary_el = p
                        break
                if cs_summary_el:
                    break

    if cs_summary_el:
        result["customers_say_summary"] = cs_summary_el.get_text(" ", strip=True)
    else:
        # Log which cr-* elements ARE present so we can diagnose missing selectors
        cr_ids = [t.get("id", "") for t in soup.find_all(id=True)
                  if "cr-" in (t.get("id", "") or "").lower()]
        cr_hooks = [t.get("data-hook", "") for t in soup.find_all(attrs={"data-hook": True})
                    if "cr-" in (t.get("data-hook", "") or "").lower()]
        logger.info(
            f"customers_say not found [{asin}] cr-ids={cr_ids[:10]} cr-hooks={cr_hooks[:10]}"
        )

    # Topic tags: "Comfort (61)", "Quality (47)" …
    topics = []
    for tag_sel in (
        "[data-hook='cr-summarization-attribute'] span",
        ".cr-lighthouse-term",
        "[data-hook='cr-insights-widget-aspects'] .a-color-base",
        "[data-hook='cr-insights-content'] .a-color-base",
        "[class*='cr-summarization-attribute'] span",
        "[data-hook^='cr-summarization-attribute']",
    ):
        els = soup.select(tag_sel)
        if els:
            seen = set()
            for el in els:
                t = el.get_text(strip=True)
                if t and t not in seen:
                    seen.add(t)
                    topics.append(t)
            break
    if topics:
        result["customers_say_topics"] = " | ".join(topics[:15])

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

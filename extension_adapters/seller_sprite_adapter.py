"""
SellerSprite (卖家精灵) extension adapter.

SellerSprite injects overlay panels into Amazon product and search pages.
This adapter attempts to read the injected DOM elements via page.evaluate().
If the extension is not installed or hasn't injected data yet, all fields
return empty strings.
"""
import logging
from .base_adapter import BaseExtensionAdapter

logger = logging.getLogger(__name__)


class SellerSpriteAdapter(BaseExtensionAdapter):
    name = "seller_sprite"

    def empty_data(self) -> dict:
        return {
            "seller_sprite_monthly_sales": "",
            "seller_sprite_monthly_revenue": "",
            "seller_sprite_rating_trend": "",
            "seller_sprite_review_growth": "",
            "seller_sprite_search_volume": "",
        }

    async def extract(self, page, asin: str) -> dict:
        """
        Read SellerSprite data from the page DOM.

        SellerSprite typically injects elements with class names containing
        Chinese keywords or specific ss- prefixed classes. The exact selectors
        depend on the installed extension version.
        """
        result = self.empty_data()

        # Wait briefly for the extension to inject its overlay
        try:
            await page.wait_for_timeout(2000)
        except Exception:
            pass

        try:
            data = await page.evaluate("""() => {
                const tryText = (selectors) => {
                    for (const sel of selectors) {
                        try {
                            const el = document.querySelector(sel);
                            if (el) {
                                const text = el.textContent.trim();
                                if (text) return text;
                            }
                        } catch (e) {}
                    }
                    return '';
                };

                // Also try walking all elements for text patterns
                const findByText = (pattern) => {
                    const allEls = document.querySelectorAll('[class*="ss-"], [class*="seller-sprite"], [class*="sellerSprite"], [data-ss], [data-seller-sprite]');
                    for (const el of allEls) {
                        const txt = el.textContent.trim();
                        if (pattern.test(txt)) return txt;
                    }
                    return '';
                };

                return {
                    monthly_sales: tryText([
                        '.ss-monthly-sales',
                        '[class*="monthlySales"]',
                        '[data-ss-sales]',
                        '[class*="ss-sales"]',
                        'div[class*="monthSales"]',
                    ]),
                    monthly_revenue: tryText([
                        '.ss-monthly-revenue',
                        '[class*="monthlyRevenue"]',
                        '[class*="monthRevenue"]',
                        '[data-ss-revenue]',
                    ]),
                    search_volume: tryText([
                        '.ss-search-volume',
                        '[class*="searchVolume"]',
                        '[class*="search-volume"]',
                        '[data-ss-volume]',
                    ]),
                    rating_trend: tryText([
                        '[class*="ratingTrend"]',
                        '[class*="rating-trend"]',
                    ]),
                    review_growth: tryText([
                        '[class*="reviewGrowth"]',
                        '[class*="review-growth"]',
                    ]),
                };
            }""")

            result["seller_sprite_monthly_sales"] = data.get("monthly_sales", "")
            result["seller_sprite_monthly_revenue"] = data.get("monthly_revenue", "")
            result["seller_sprite_search_volume"] = data.get("search_volume", "")
            result["seller_sprite_rating_trend"] = data.get("rating_trend", "")
            result["seller_sprite_review_growth"] = data.get("review_growth", "")

        except Exception as exc:
            logger.debug(f"SellerSprite adapter error for {asin}: {exc}")

        return result

"""
SIF (Seller Investigation Framework / similar Amazon seller tool) extension adapter.

SIF injects overlay data on Amazon product pages. This adapter reads the
injected DOM elements. If the extension is not installed, all fields are empty.
"""
import logging
from .base_adapter import BaseExtensionAdapter

logger = logging.getLogger(__name__)


class SIFAdapter(BaseExtensionAdapter):
    name = "sif"

    def empty_data(self) -> dict:
        return {
            "sif_monthly_sales": "",
            "sif_seller_count": "",
            "sif_listing_date": "",
            "sif_variation_count": "",
        }

    async def extract(self, page, asin: str) -> dict:
        """
        Read SIF extension data from the page DOM.

        SIF typically injects elements with sif- prefixed class names or
        data-sif attributes into the Amazon product page.
        """
        result = self.empty_data()

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

                return {
                    monthly_sales: tryText([
                        '[class*="sif-sales"]',
                        '[class*="sifSales"]',
                        '[data-sif-sales]',
                        '[class*="sif-monthly"]',
                        '[class*="sifMonthly"]',
                    ]),
                    seller_count: tryText([
                        '[class*="sif-seller-count"]',
                        '[class*="sifSellerCount"]',
                        '[data-sif-sellers]',
                        '[class*="seller-count"]',
                    ]),
                    listing_date: tryText([
                        '[class*="sif-listing-date"]',
                        '[class*="sifListingDate"]',
                        '[data-sif-date]',
                    ]),
                    variation_count: tryText([
                        '[class*="sif-variation"]',
                        '[class*="sifVariation"]',
                        '[data-sif-variations]',
                    ]),
                };
            }""")

            result["sif_monthly_sales"] = data.get("monthly_sales", "")
            result["sif_seller_count"] = data.get("seller_count", "")
            result["sif_listing_date"] = data.get("listing_date", "")
            result["sif_variation_count"] = data.get("variation_count", "")

        except Exception as exc:
            logger.debug(f"SIF adapter error for {asin}: {exc}")

        return result

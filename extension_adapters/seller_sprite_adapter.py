"""
SellerSprite (卖家精灵) extension adapter — sync version.

Reads the overlay panel injected by 卖家精灵 on Amazon product detail pages.
Uses label-based DOM search because SellerSprite class names change across
extension versions.  All fields return "" when the extension is absent.
"""
import logging
from .base_adapter import BaseExtensionAdapter

logger = logging.getLogger(__name__)


class SellerSpriteAdapter(BaseExtensionAdapter):
    name = "seller_sprite"

    def empty_data(self) -> dict:
        return {
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
        }

    def extract_sync(self, page, asin: str) -> dict:
        """
        Read SellerSprite data from the live Playwright page (sync).
        Called after navigate + scroll so the extension has had time to render.
        """
        result = self.empty_data()
        try:
            data = page.evaluate("""() => {
                // Find the text content of the element that immediately follows
                // a label element whose text contains the given keyword.
                function findByLabel(keywords) {
                    const all = Array.from(document.querySelectorAll('*'));
                    for (const el of all) {
                        const txt = (el.textContent || '').trim();
                        for (const kw of keywords) {
                            if (txt === kw || txt.startsWith(kw + ':') || txt.startsWith(kw + '：')) {
                                // Try next sibling or parent's next sibling
                                let sib = el.nextElementSibling;
                                if (sib) {
                                    const v = sib.textContent.trim();
                                    if (v && v !== kw) return v;
                                }
                                // Try parent container — find sibling spans/divs
                                const parent = el.parentElement;
                                if (parent) {
                                    for (const child of parent.children) {
                                        if (child !== el) {
                                            const v = child.textContent.trim();
                                            if (v && v !== kw) return v;
                                        }
                                    }
                                }
                            }
                        }
                    }
                    return '';
                }

                // Also scan by visible text pattern in known extension containers
                function findInPanel(labels) {
                    // 卖家精灵 typically injects a panel with class containing 'SellerSprite' or 'ss-'
                    const panels = document.querySelectorAll(
                        '[class*="sellerSprite"], [class*="SellerSprite"], [class*="ss-panel"], ' +
                        '[class*="seller-sprite"], [id*="sellerSprite"], [id*="SellerSprite"]'
                    );
                    const targets = panels.length ? Array.from(panels) : [document.body];
                    for (const container of targets) {
                        const items = container.querySelectorAll('*');
                        for (const el of items) {
                            const txt = (el.textContent || '').trim();
                            for (const lbl of labels) {
                                if (txt.includes(lbl)) {
                                    let sib = el.nextElementSibling;
                                    if (sib) {
                                        const v = sib.textContent.trim();
                                        if (v) return v;
                                    }
                                    // Value may be in same element after colon
                                    const parts = txt.split(/[:：]/);
                                    if (parts.length >= 2) return parts.slice(1).join(':').trim();
                                }
                            }
                        }
                    }
                    return '';
                }

                return {
                    monthly_sales_parent: findByLabel(['近30天销量(父体)', '月销量(父)', '近30天销量']) ||
                                          findInPanel(['近30天销量(父体)', '月销量(父)']),
                    monthly_sales_child:  findByLabel(['近30天销量(子体)', '月销量(子)']) ||
                                          findInPanel(['近30天销量(子体)', '月销量(子)']),
                    monthly_revenue:      findByLabel(['销售额', '月销售额', '近30天销售额']) ||
                                          findInPanel(['销售额', '月销售额']),
                    fba_fee:              findByLabel(['FBA费用', 'FBA Fee', 'FBA配送费']) ||
                                          findInPanel(['FBA费用']),
                    gross_margin:         findByLabel(['毛利率', '利润率']) ||
                                          findInPanel(['毛利率', '利润率']),
                    shipping_days:        findByLabel(['配送时长', '配送天数', '发货时效']) ||
                                          findInPanel(['配送时长', '配送天数']),
                    total_traffic:        findByLabel(['全部流量', '总流量']) ||
                                          findInPanel(['全部流量', '总流量']),
                    organic_traffic:      findByLabel(['自然搜索词', '自然流量']) ||
                                          findInPanel(['自然搜索词', '自然流量']),
                    ad_traffic:           findByLabel(['广告流量', '广告词']) ||
                                          findInPanel(['广告流量', '广告词']),
                    recommend_traffic:    findByLabel(['搜索推荐', '关联推荐']) ||
                                          findInPanel(['搜索推荐']),
                };
            }""")

            result["ss_monthly_sales_parent"] = data.get("monthly_sales_parent", "")
            result["ss_monthly_sales_child"]  = data.get("monthly_sales_child", "")
            result["ss_monthly_revenue"]      = data.get("monthly_revenue", "")
            result["ss_fba_fee"]              = data.get("fba_fee", "")
            result["ss_gross_margin"]         = data.get("gross_margin", "")
            result["ss_shipping_days"]        = data.get("shipping_days", "")
            result["ss_total_traffic"]        = data.get("total_traffic", "")
            result["ss_organic_traffic"]      = data.get("organic_traffic", "")
            result["ss_ad_traffic"]           = data.get("ad_traffic", "")
            result["ss_recommend_traffic"]    = data.get("recommend_traffic", "")

        except Exception as exc:
            logger.debug(f"SellerSprite adapter error for {asin}: {exc}")

        return result

    # Keep async stub so the class still satisfies BaseExtensionAdapter
    async def extract(self, page, asin: str) -> dict:
        return self.empty_data()

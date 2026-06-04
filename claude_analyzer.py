"""
Claude API integration for Amazon product analysis.
Uses claude-sonnet-4-6 to score products and give Go/Maybe/No-Go recommendations.
"""

import json
import os
import anthropic


def analyze_product(data: dict) -> dict:
    """
    Analyze an Amazon product using Claude API.

    Args:
        data: Dictionary containing all product metrics

    Returns:
        Dictionary with scores, verdict, reasoning, risks, and opportunities
    """
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    prompt = _build_prompt(data)

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system="""你是一位专业的亚马逊产品选品顾问，拥有多年跨境电商经验。
你的任务是基于提供的产品数据，进行全面的选品分析，并以JSON格式返回结构化的评分和建议。

评分标准：
- 市场机会 (Market Opportunity) 0-10分：基于月销量、趋势、未被满足的需求
- 盈利能力 (Profitability) 0-10分：基于毛利润、毛润率、FBA成本、头程费用
- 竞争程度 (Competition Level) 0-10分：分数越低代表竞争越激烈（对卖家越不利），分数越高代表竞争越少（对卖家越有利）
- 产品质量信号 (Product Quality Signal) 0-10分：基于评分、优缺点分析、退货率
- 趋势与持续性 (Trend & Longevity) 0-10分：基于近3年趋势数据

综合评分 (Overall Score) = 各维度加权平均分
判断标准：
- 综合评分 >= 7：Go（建议跟进）
- 综合评分 5-7：Maybe（需要进一步调查）
- 综合评分 < 5：No-Go（不建议）

你必须以下面的JSON格式返回结果，不要包含任何其他内容：
{
  "market_opportunity": <0-10的数字>,
  "profitability": <0-10的数字>,
  "competition_level": <0-10的数字>,
  "product_quality_signal": <0-10的数字>,
  "trend_longevity": <0-10的数字>,
  "overall_score": <0-10的数字>,
  "verdict": "<Go|Maybe|No-Go>",
  "reasoning": "<详细的分析理由，包括各维度的具体分析>",
  "key_risks": ["<风险1>", "<风险2>", "<风险3>"],
  "key_opportunities": ["<机会1>", "<机会2>", "<机会3>"]
}""",
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ]
    )

    raw_text = response.content[0].text.strip()

    # Extract JSON from response
    if "```json" in raw_text:
        raw_text = raw_text.split("```json")[1].split("```")[0].strip()
    elif "```" in raw_text:
        raw_text = raw_text.split("```")[1].split("```")[0].strip()

    result = json.loads(raw_text)

    # Ensure verdict is set correctly based on overall_score if not already set
    score = float(result.get("overall_score", 0))
    if "verdict" not in result or not result["verdict"]:
        if score >= 7:
            result["verdict"] = "Go"
        elif score >= 5:
            result["verdict"] = "Maybe"
        else:
            result["verdict"] = "No-Go"

    # Ensure all required fields exist
    result.setdefault("market_opportunity", 0)
    result.setdefault("profitability", 0)
    result.setdefault("competition_level", 0)
    result.setdefault("product_quality_signal", 0)
    result.setdefault("trend_longevity", 0)
    result.setdefault("overall_score", score)
    result.setdefault("reasoning", "")
    result.setdefault("key_risks", [])
    result.setdefault("key_opportunities", [])

    return result


def _build_prompt(data: dict) -> str:
    """Build a comprehensive prompt with all product data."""

    def val(key, default="未提供"):
        v = data.get(key)
        if v is None or v == "" or v == []:
            return default
        return v

    prompt = f"""请分析以下亚马逊产品的选品数据：

【基本信息】
- 产品名称：{val('product_name')}
- 品牌：{val('brand')}
- 热销ASIN：{val('top_asin')}
- 类目节点：{val('category_node')}

【销量数据】
- 热销ASIN月销量：{val('top_asin_monthly_sales')}
- 父体月销量：{val('parent_monthly_sales')}
- 变体数量：{val('variants')}
- 转化率：{val('conversion_rate')}

【竞争分析】
- 竞店商品相关度：{val('competitor_relevance')}
- 卖家注册地：{val('seller_origin')}
- 店铺年feedback：{val('annual_feedback')}
- 评分：{val('rating')}
- 评论数：{val('reviews')}
- 上架时间：{val('launch_date')}
- 品牌/卖家/商品集中度：{val('concentration')}
- 广告占比：{val('ad_share')}

【价格与财务】
- 成交金额：{val('transaction_price')}
- 促销coupon：{val('coupon')}
- 历史价格：{val('historical_price')}
- 产品成本(人民币)：{val('product_cost_rmb')}
- 产品成本(美金)：{val('product_cost_usd')}
- 平台佣金：{val('platform_commission')}
- FBA费用：{val('fba')}
- 毛利润：{val('gross_profit')}
- 毛润率：{val('gross_margin')}
- 汇率：{val('exchange_rate')}

【物流信息】
- 包裹重：{val('package_weight')}
- 体积重：{val('volume_weight')}
- 包裹尺寸（长×宽×高）：{val('package_length')} × {val('package_width')} × {val('package_height')}
- 头程-重量：{val('first_leg_weight')}
- 头程-尺寸：{val('first_leg_size')}
- 头程费用：{val('first_leg_shipping')}
- 当前头程价：{val('current_first_leg_price')}
- 淡季仓储费：{val('off_season_storage')}

【广告数据】
- CPC：{val('cpc')}
- 投产比：{val('ad_roi')}
- 广告占比：{val('ad_share')}

【关键词与趋势】
- 关键词1：{val('keyword1')} | 近3年趋势：{val('trend1')}
- 关键词2：{val('keyword2')} | 近3年趋势：{val('trend2')}
- 关键词3：{val('keyword3')} | 近3年趋势：{val('trend3')}
- 关键词4：{val('keyword4')} | 近3年趋势：{val('trend4')}
- 关键词5：{val('keyword5')} | 近3年趋势：{val('trend5')}
- 热销ASIN近3年趋势：{val('top_asin_trend')}

【视觉质量】
- 图片：{val('visual_images')}
- 主图视频：{val('visual_video')}
- A+内容：{val('visual_aplus')}

【消费者洞察】
- 消费者画像：{val('consumer_profile')}
- 使用场景：{val('use_cases')}
- 未被满足的需求：{val('unmet_needs')}
- 优点：{val('pros')}
- 商机探测器优点：{val('opportunity_pros')}
- 缺点：{val('cons')}
- 商机探测器缺点：{val('opportunity_cons')}
- 购买动机：{val('purchase_motivation')}
- 特点评分：{val('feature_ratings')}
- 商机探测器退货原因：{val('return_reasons')}
- 复购周期：{val('repurchase_cycle')}
- 退货率：{val('return_rate')}

【营销信息】
- 标题：{val('title')}
- 卖点：{val('selling_points')}
- 广告：{val('ads')}

请基于以上数据，严格按照系统提示中的JSON格式进行分析并返回结果。"""

    return prompt

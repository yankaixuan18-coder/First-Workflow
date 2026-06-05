"""
AI product evaluator.

Given a collected product dict, ask an LLM for a concise 选品评价 (sourcing
evaluation) in Chinese. Supports multiple providers via their REST APIs using
only the standard library (no extra dependencies):

    anthropic  -> Claude   (api.anthropic.com)
    openai     -> GPT      (api.openai.com)
    deepseek   -> DeepSeek (api.deepseek.com)
    gemini     -> Gemini   (generativelanguage.googleapis.com)

The API key is supplied by the user at run time (never stored). All errors are
caught and returned as a short message so collection never crashes.
"""
import json
import logging
import urllib.request
import urllib.error

logger = logging.getLogger(__name__)

# Sensible default model per provider (user can override in the UI).
DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-4-6",
    "openai": "gpt-4o-mini",
    "deepseek": "deepseek-chat",
    "gemini": "gemini-1.5-flash",
}

PROVIDER_LABELS = {
    "anthropic": "Claude (Anthropic)",
    "openai": "OpenAI GPT",
    "deepseek": "DeepSeek",
    "gemini": "Google Gemini",
}

# Fields fed to the model, in a readable label -> key form.
_PROMPT_FIELDS = [
    ("标题", "title"),
    ("品牌", "brand"),
    ("售价", "price"),
    ("评分", "rating"),
    ("评论数", "review_count"),
    ("BSR排名", "bsr"),
    ("主类目", "main_category"),
    ("月销量(父体)", "ss_monthly_sales_parent"),
    ("月销售额", "ss_monthly_revenue"),
    ("FBA费用", "ss_fba_fee"),
    ("毛利率", "ss_gross_margin"),
    ("卖家数", "sif_seller_count"),
    ("上架时间", "listing_date"),
    ("变体数", "variation_count"),
    ("商品重量", "item_weight"),
    ("包装尺寸", "package_dimensions"),
    ("卖点", "bullet_points"),
]

_SYSTEM_PROMPT = (
    "你是一位资深的亚马逊选品分析师。根据给定的产品数据，给出简洁专业的选品评价。"
    "请用中文，控制在120字以内，包含：是否值得切入、主要优势、主要风险/劣势。"
    "直接给结论，不要客套话。"
)

_MARKET_SYSTEM_PROMPT = (
    "你是一位资深的亚马逊市场分析与选品专家。下面是某个关键词下采集到的一批竞品数据。"
    "请基于整体数据做市场分析，用中文给出结构化的选品结论，包含以下部分（用小标题）：\n"
    "1. 市场概况（容量/需求/价格带分布）\n"
    "2. 竞争格局（头部集中度/卖家分散度/评论壁垒）\n"
    "3. 利润空间（毛利率/FBA费/价格区间的盈利性）\n"
    "4. 机会点（差异化空间、细分切入点）\n"
    "5. 风险与壁垒\n"
    "6. 最终结论（是否值得进入、建议的切入策略与定价区间）\n"
    "用数据支撑判断，结论要明确。总字数控制在500字以内。"
)


def _build_prompt(product: dict) -> str:
    lines = ["请评价以下亚马逊产品："]
    for label, key in _PROMPT_FIELDS:
        val = str(product.get(key, "") or "").strip()
        if val:
            lines.append(f"- {label}: {val[:200]}")
    return "\n".join(lines)


def _num(value):
    """Extract a float from messy strings like '$54.99', '4,042', '3,000+'."""
    import re
    if value is None:
        return None
    m = re.search(r"-?\d+(\.\d+)?", str(value).replace(",", ""))
    return float(m.group(0)) if m else None


def _build_market_prompt(products: list, keyword: str) -> str:
    prices, sales, revenues, margins, reviews, ratings = [], [], [], [], [], []
    sellers = set()
    for p in products:
        for src, dst in (("price", prices), ("ss_monthly_sales_parent", sales),
                         ("ss_monthly_revenue", revenues), ("ss_gross_margin", margins),
                         ("review_count", reviews), ("rating", ratings)):
            v = _num(p.get(src))
            if v is not None:
                dst.append(v)
        s = str(p.get("seller_name", "") or "").strip()
        if s:
            sellers.add(s)

    def stat(arr):
        return f"最低{min(arr):.1f} / 平均{sum(arr)/len(arr):.1f} / 最高{max(arr):.1f}" if arr else "无数据"

    lines = [
        f"关键词: {keyword}",
        f"采集竞品数量: {len(products)}",
        f"售价区间(美元): {stat(prices)}",
        f"月销量(父体)区间: {stat(sales)}",
        f"月销售额(美元)区间: {stat(revenues)}",
        f"毛利率(%)区间: {stat(margins)}",
        f"评论数区间: {stat(reviews)}",
        f"评分区间: {stat(ratings)}",
        f"不同卖家数量: {len(sellers)}",
        "",
        "逐个产品概览（标题|售价|月销量|月销售额|毛利率|评分|评论数|卖家）：",
    ]
    for i, p in enumerate(products, 1):
        lines.append(
            f"{i}. {str(p.get('title',''))[:50]} | "
            f"{p.get('price','')} | 月销{p.get('ss_monthly_sales_parent','')} | "
            f"{p.get('ss_monthly_revenue','')} | 毛利{p.get('ss_gross_margin','')} | "
            f"评分{p.get('rating','')} | 评论{p.get('review_count','')} | "
            f"{p.get('seller_name','')}"
        )
    return "\n".join(lines)


def _run(provider: str, api_key: str, model: str, system: str, prompt: str,
         max_tokens: int, timeout: int) -> str:
    """Dispatch a single chat completion to the chosen provider."""
    provider = (provider or "").lower().strip()
    model = (model or "").strip() or DEFAULT_MODELS.get(provider, "")
    if not api_key:
        return "[未提供API Key]"
    if provider not in DEFAULT_MODELS:
        return f"[不支持的模型提供商: {provider}]"
    try:
        if provider == "anthropic":
            return _call_anthropic(api_key, model, system, prompt, max_tokens, timeout)
        if provider in ("openai", "deepseek"):
            return _call_openai_compatible(provider, api_key, model, system, prompt, max_tokens, timeout)
        if provider == "gemini":
            return _call_gemini(api_key, model, system, prompt, timeout)
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", "ignore")[:200]
        except Exception:
            pass
        logger.warning(f"AI HTTP {e.code}: {body}")
        return f"[AI错误 HTTP {e.code}: {body}]"
    except Exception as e:
        logger.warning(f"AI error: {e}")
        return f"[AI错误: {e}]"
    return "[未知错误]"


def evaluate(product: dict, provider: str, api_key: str, model: str = "", timeout: int = 60) -> str:
    """Return an AI evaluation string for ONE product, or an error message."""
    return _run(provider, api_key, model, _SYSTEM_PROMPT, _build_prompt(product),
                max_tokens=400, timeout=timeout)


def evaluate_market(products: list, keyword: str, provider: str, api_key: str,
                    model: str = "", timeout: int = 120) -> str:
    """Analyze the WHOLE keyword's dataset and return a market sourcing conclusion."""
    if not products:
        return "[无数据]"
    return _run(provider, api_key, model, _MARKET_SYSTEM_PROMPT,
                _build_market_prompt(products, keyword),
                max_tokens=1200, timeout=timeout)


def _post(url: str, headers: dict, payload: dict, timeout: int) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _call_anthropic(api_key: str, model: str, system: str, prompt: str,
                    max_tokens: int, timeout: int) -> str:
    out = _post(
        "https://api.anthropic.com/v1/messages",
        {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        {
            "model": model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout,
    )
    parts = out.get("content", [])
    return "".join(p.get("text", "") for p in parts).strip() or "[空响应]"


def _call_openai_compatible(provider: str, api_key: str, model: str, system: str,
                            prompt: str, max_tokens: int, timeout: int) -> str:
    base = "https://api.openai.com/v1" if provider == "openai" else "https://api.deepseek.com"
    out = _post(
        f"{base}/chat/completions",
        {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        {
            "model": model,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        },
        timeout,
    )
    choices = out.get("choices", [])
    if choices:
        return (choices[0].get("message", {}).get("content", "") or "").strip() or "[空响应]"
    return "[空响应]"


def _call_gemini(api_key: str, model: str, system: str, prompt: str, timeout: int) -> str:
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={api_key}"
    )
    out = _post(
        url,
        {"Content-Type": "application/json"},
        {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"parts": [{"text": prompt}]}],
        },
        timeout,
    )
    cands = out.get("candidates", [])
    if cands:
        parts = cands[0].get("content", {}).get("parts", [])
        return "".join(p.get("text", "") for p in parts).strip() or "[空响应]"
    return "[空响应]"

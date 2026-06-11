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
         max_tokens: int, timeout: int, retries: int = 2) -> str:
    """Dispatch a single chat completion to the chosen provider.

    Retries up to `retries` times on empty / filter responses (DeepSeek
    occasionally returns an empty content block when rate-limited or when its
    content policy fires, but succeeds on retry).
    """
    import time as _time

    provider = (provider or "").lower().strip()
    model = (model or "").strip() or DEFAULT_MODELS.get(provider, "")
    if not api_key:
        return "[未提供API Key]"
    if provider not in DEFAULT_MODELS:
        return f"[不支持的模型提供商: {provider}]"

    last_result = "[未知错误]"
    for attempt in range(1 + retries):
        try:
            if provider == "anthropic":
                result = _call_anthropic(api_key, model, system, prompt, max_tokens, timeout)
            elif provider in ("openai", "deepseek"):
                result = _call_openai_compatible(provider, api_key, model, system, prompt, max_tokens, timeout)
            elif provider == "gemini":
                result = _call_gemini(api_key, model, system, prompt, timeout)
            else:
                result = "[未知错误]"
        except Exception as e:
            logger.warning(f"AI error (attempt {attempt+1}): {e}")
            result = f"[AI错误: {e}]"

        last_result = result
        # Retry only on empty/filtered responses — not on real errors or actual content
        if result and not result.startswith("[空响应") and not result.startswith("[AI错误:"):
            return result
        if attempt < retries:
            wait = 2.0 * (attempt + 1)
            logger.info(f"AI returned empty/error on attempt {attempt+1}, retrying in {wait:.0f}s …")
            _time.sleep(wait)

    return last_result


def evaluate(product: dict, provider: str, api_key: str, model: str = "", timeout: int = 60) -> str:
    """Return an AI evaluation string for ONE product, or an error message."""
    # Generous token budget: reasoning models (e.g. deepseek-v4-pro) spend
    # tokens on hidden reasoning before the answer, so a small cap can truncate
    # the visible content to empty (finish_reason='length').
    return _run(provider, api_key, model, _SYSTEM_PROMPT, _build_prompt(product),
                max_tokens=1200, timeout=timeout)


def evaluate_market(products: list, keyword: str, provider: str, api_key: str,
                    model: str = "", timeout: int = 120) -> str:
    """Analyze the WHOLE keyword's dataset and return a market sourcing conclusion."""
    if not products:
        return "[无数据]"
    return _run(provider, api_key, model, _MARKET_SYSTEM_PROMPT,
                _build_market_prompt(products, keyword),
                max_tokens=1200, timeout=timeout)


_CATEGORIZE_SYSTEM_PROMPT = (
    "你是一位亚马逊选品专家。给定一批产品标题，请将它们归类到有意义的产品小类中。\n"
    "要求：\n"
    "1. 根据产品标题的实际差异（尺寸/材质/适用人群/功能/设计特点等），划分出1-8个有意义的小类。\n"
    "   分类示例：大号保温袋 / 背包式保温袋 / 迷你保温袋 / 成人款 / 儿童款 / 高端品牌款 等。\n"
    "2. 每个产品必须分配到一个类别，不能遗漏。\n"
    '3. 【重要】禁止使用「其他」「其它」「未分类」「其他产品」「杂项」等兜底类别名称。\n'
    '   如果所有产品都很相似，就把它们全部放到同一个描述性名称的类别里。\n'
    "4. 严格按照以下JSON格式输出，不要有任何额外文字：\n"
    '{"categories": [{"name": "类别名称", "asins": ["B0XXXXX", "B0YYYYY"]}, ...]}'
)


def categorize_products(products: list, provider: str, api_key: str,
                        model: str = "", timeout: int = 120) -> dict:
    """
    Use AI to group products by category based on their titles.
    Returns a dict: {category_name: [asin, ...], ...}
    On failure returns {"未分类": [all asins]}.
    """
    if not products:
        return {}

    lines = []
    for p in products:
        asin = p.get("asin", "")
        title = str(p.get("title", ""))[:120]
        lines.append(f"{asin}: {title}")

    prompt = "请对以下产品进行分类：\n" + "\n".join(lines)
    raw = _run(provider, api_key, model, _CATEGORIZE_SYSTEM_PROMPT,
               prompt, max_tokens=2000, timeout=timeout)

    logger.info(f"Categorize raw response ({len(raw)} chars): {raw[:400]}")

    import re as _re
    # Extract JSON from response (model may wrap it in markdown code blocks)
    m = _re.search(r'\{.*"categories".*\}', raw, _re.DOTALL)
    if not m:
        logger.warning(f"Categorize: no JSON found in response: {raw[:300]}")
        return {"同类产品": [p.get("asin", "") for p in products]}

    _CATCHALL_NAMES = {
        "其他", "其它", "未分类", "其他类别", "其他产品", "杂项", "miscellaneous",
        "others", "other", "uncategorized", "unclassified",
    }

    try:
        data = json.loads(m.group(0))
        result = {}
        catchall_asins = []
        for cat in data.get("categories", []):
            name = str(cat.get("name", "")).strip()
            asins = [str(a).strip() for a in cat.get("asins", []) if a]
            if not name or not asins:
                continue
            # Detect AI-created catch-all names and defer redistribution
            if name.lower().rstrip("0123456789 、，,。.") in _CATCHALL_NAMES:
                logger.info(f"Categorize: AI used catch-all name '{name}' with {len(asins)} asins — redistributing")
                catchall_asins.extend(asins)
            else:
                result[name] = result.get(name, []) + asins

        # Redistribute catch-all products: put them in the largest real category,
        # or create one based on the first product's title if no real categories exist.
        if catchall_asins:
            if result:
                # Put them in the biggest existing category
                biggest = max(result, key=lambda k: len(result[k]))
                result[biggest] = result[biggest] + catchall_asins
            else:
                # All products went to catch-all — create one descriptive category
                first_title = ""
                asin_to_title = {p.get("asin", ""): str(p.get("title", ""))[:40] for p in products}
                for a in catchall_asins:
                    if asin_to_title.get(a):
                        first_title = asin_to_title[a]
                        break
                cat_name = first_title or "同类产品"
                result[cat_name] = catchall_asins

        return result if result else {"同类产品": [p.get("asin", "") for p in products]}
    except Exception as e:
        logger.warning(f"Categorize JSON parse error: {e}")
        return {"同类产品": [p.get("asin", "") for p in products]}


def _post(url: str, headers: dict, payload: dict, timeout: int) -> dict:
    import http.client
    import ssl
    from urllib.parse import urlparse

    # ensure_ascii=True (default) keeps body bytes pure ASCII so no encoding issues
    data = json.dumps(payload, ensure_ascii=True).encode("utf-8")

    parsed = urlparse(url)
    host = parsed.netloc
    path = parsed.path + (("?" + parsed.query) if parsed.query else "")

    ctx = ssl.create_default_context()
    conn = http.client.HTTPSConnection(host, timeout=timeout, context=ctx)
    try:
        # Build headers with only ASCII values (api keys, content-type)
        safe_headers = {k: str(v).encode("ascii", "replace").decode("ascii")
                        for k, v in headers.items()}
        safe_headers["Content-Type"] = "application/json"
        safe_headers["Content-Length"] = str(len(data))
        conn.request("POST", path, body=data, headers=safe_headers)
        resp = conn.getresponse()
        raw = resp.read()
        if resp.status >= 400:
            snippet = raw.decode("utf-8", "ignore")[:200]
            logger.warning(f"AI HTTP {resp.status}: {snippet}")
            raise RuntimeError(f"HTTP {resp.status}: {snippet}")
        return json.loads(raw.decode("utf-8"))
    finally:
        conn.close()


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
        msg = choices[0].get("message", {}) or {}
        content = (msg.get("content", "") or "").strip()
        if content:
            return content
        # Some reasoning models leave content empty but fill reasoning_content;
        # fall back to it rather than reporting nothing.
        reasoning = (msg.get("reasoning_content", "") or "").strip()
        if reasoning:
            return reasoning
        finish = choices[0].get("finish_reason", "")
        logger.warning(f"Empty content from {provider}, finish_reason={finish!r}")
        # finish_reason='length' means max_tokens truncated everything → signal caller
        return "[空响应:length]" if finish == "length" else "[空响应]"
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

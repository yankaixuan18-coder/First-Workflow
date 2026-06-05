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


def _build_prompt(product: dict) -> str:
    lines = ["请评价以下亚马逊产品："]
    for label, key in _PROMPT_FIELDS:
        val = str(product.get(key, "") or "").strip()
        if val:
            lines.append(f"- {label}: {val[:200]}")
    return "\n".join(lines)


def evaluate(product: dict, provider: str, api_key: str, model: str = "", timeout: int = 60) -> str:
    """Return an AI evaluation string for one product, or an error message."""
    provider = (provider or "").lower().strip()
    model = (model or "").strip() or DEFAULT_MODELS.get(provider, "")
    if not api_key:
        return "[未提供API Key]"
    if provider not in DEFAULT_MODELS:
        return f"[不支持的模型提供商: {provider}]"

    prompt = _build_prompt(product)
    try:
        if provider == "anthropic":
            return _call_anthropic(api_key, model, prompt, timeout)
        if provider in ("openai", "deepseek"):
            return _call_openai_compatible(provider, api_key, model, prompt, timeout)
        if provider == "gemini":
            return _call_gemini(api_key, model, prompt, timeout)
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", "ignore")[:200]
        except Exception:
            pass
        logger.warning(f"AI eval HTTP {e.code}: {body}")
        return f"[AI错误 HTTP {e.code}: {body}]"
    except Exception as e:
        logger.warning(f"AI eval error: {e}")
        return f"[AI错误: {e}]"
    return "[未知错误]"


def _post(url: str, headers: dict, payload: dict, timeout: int) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _call_anthropic(api_key: str, model: str, prompt: str, timeout: int) -> str:
    out = _post(
        "https://api.anthropic.com/v1/messages",
        {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        {
            "model": model,
            "max_tokens": 400,
            "system": _SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout,
    )
    parts = out.get("content", [])
    return "".join(p.get("text", "") for p in parts).strip() or "[空响应]"


def _call_openai_compatible(provider: str, api_key: str, model: str, prompt: str, timeout: int) -> str:
    base = "https://api.openai.com/v1" if provider == "openai" else "https://api.deepseek.com"
    out = _post(
        f"{base}/chat/completions",
        {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        {
            "model": model,
            "max_tokens": 400,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        },
        timeout,
    )
    choices = out.get("choices", [])
    if choices:
        return (choices[0].get("message", {}).get("content", "") or "").strip() or "[空响应]"
    return "[空响应]"


def _call_gemini(api_key: str, model: str, prompt: str, timeout: int) -> str:
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={api_key}"
    )
    out = _post(
        url,
        {"Content-Type": "application/json"},
        {
            "systemInstruction": {"parts": [{"text": _SYSTEM_PROMPT}]},
            "contents": [{"parts": [{"text": prompt}]}],
        },
        timeout,
    )
    cands = out.get("candidates", [])
    if cands:
        parts = cands[0].get("content", {}).get("parts", [])
        return "".join(p.get("text", "") for p in parts).strip() or "[空响应]"
    return "[空响应]"

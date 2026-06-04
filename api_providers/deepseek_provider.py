"""
DeepSeek provider.
DeepSeek's API is OpenAI-compatible, so we use the openai SDK with a custom base_url.
Requires: pip install openai
"""
from .base import BaseProvider

_SDK_AVAILABLE = False
try:
    import openai as _openai_sdk
    _SDK_AVAILABLE = True
except ImportError:
    pass

DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"


class DeepSeekProvider(BaseProvider):
    provider_name = "deepseek"

    def __init__(self, api_key: str = "", **kwargs):
        super().__init__(api_key=api_key, **kwargs)

    def complete(self, prompt: str, system: str = "", **kwargs) -> str:
        if not _SDK_AVAILABLE:
            raise NotImplementedError(
                "The 'openai' package is not installed (needed for DeepSeek). "
                "Run: pip install openai"
            )
        if not self.api_key:
            raise NotImplementedError(
                "DEEPSEEK_API_KEY is not set. "
                "Add it to your .env file: DEEPSEEK_API_KEY=sk-..."
            )
        client = _openai_sdk.OpenAI(
            api_key=self.api_key,
            base_url=self.config.get("base_url", DEEPSEEK_BASE_URL),
        )
        model = kwargs.get("model", "deepseek-chat")
        max_tokens = kwargs.get("max_tokens", 1024)
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        response = client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            messages=messages,
        )
        return response.choices[0].message.content

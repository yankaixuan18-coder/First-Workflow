"""
OpenAI provider.
Requires: pip install openai
"""
from .base import BaseProvider

_SDK_AVAILABLE = False
try:
    import openai as _openai_sdk
    _SDK_AVAILABLE = True
except ImportError:
    pass


class OpenAIProvider(BaseProvider):
    provider_name = "openai"

    def __init__(self, api_key: str = "", **kwargs):
        super().__init__(api_key=api_key, **kwargs)

    def complete(self, prompt: str, system: str = "", **kwargs) -> str:
        if not _SDK_AVAILABLE:
            raise NotImplementedError(
                "The 'openai' package is not installed. "
                "Run: pip install openai"
            )
        if not self.api_key:
            raise NotImplementedError(
                "OPENAI_API_KEY is not set. "
                "Add it to your .env file: OPENAI_API_KEY=sk-..."
            )
        client = _openai_sdk.OpenAI(api_key=self.api_key)
        model = kwargs.get("model", "gpt-4o-mini")
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

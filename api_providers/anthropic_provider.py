"""
Anthropic Claude provider.
Requires: pip install anthropic
"""
from .base import BaseProvider

_SDK_AVAILABLE = False
try:
    import anthropic as _anthropic_sdk
    _SDK_AVAILABLE = True
except ImportError:
    pass


class AnthropicProvider(BaseProvider):
    provider_name = "anthropic"

    def __init__(self, api_key: str = "", **kwargs):
        super().__init__(api_key=api_key, **kwargs)

    def complete(self, prompt: str, system: str = "", **kwargs) -> str:
        if not _SDK_AVAILABLE:
            raise NotImplementedError(
                "The 'anthropic' package is not installed. "
                "Run: pip install anthropic"
            )
        if not self.api_key:
            raise NotImplementedError(
                "ANTHROPIC_API_KEY is not set. "
                "Add it to your .env file: ANTHROPIC_API_KEY=sk-ant-..."
            )
        client = _anthropic_sdk.Anthropic(api_key=self.api_key)
        model = kwargs.get("model", "claude-sonnet-4-6")
        max_tokens = kwargs.get("max_tokens", 1024)
        messages = [{"role": "user", "content": prompt}]
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system if system else None,
            messages=messages,
        )
        return response.content[0].text

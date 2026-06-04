from .base import BaseProvider
from .anthropic_provider import AnthropicProvider
from .openai_provider import OpenAIProvider
from .gemini_provider import GeminiProvider
from .deepseek_provider import DeepSeekProvider

PROVIDERS = {
    "anthropic": AnthropicProvider,
    "openai": OpenAIProvider,
    "gemini": GeminiProvider,
    "deepseek": DeepSeekProvider,
}


def get_provider(name: str, api_key: str = "", **kwargs) -> BaseProvider:
    """
    Instantiate and return an LLM provider by name.

    Args:
        name: Provider name — one of "anthropic", "openai", "gemini", "deepseek".
        api_key: API key for the provider.
        **kwargs: Additional provider-specific configuration.

    Raises:
        ValueError: If the provider name is not recognized.
    """
    cls = PROVIDERS.get(name)
    if not cls:
        raise ValueError(
            f"Unknown provider: {name!r}. Available providers: {list(PROVIDERS)}"
        )
    return cls(api_key=api_key, **kwargs)


__all__ = [
    "BaseProvider",
    "AnthropicProvider",
    "OpenAIProvider",
    "GeminiProvider",
    "DeepSeekProvider",
    "PROVIDERS",
    "get_provider",
]

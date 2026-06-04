"""
Abstract base class for LLM API providers.
Providers are optional — they are not used for data collection.
"""
from abc import ABC, abstractmethod


class BaseProvider(ABC):
    provider_name: str = "base"

    def __init__(self, api_key: str = "", **kwargs):
        self.api_key = api_key
        self.config = kwargs

    @abstractmethod
    def complete(self, prompt: str, system: str = "", **kwargs) -> str:
        """
        Send a completion request to the LLM.

        Args:
            prompt: The user message / prompt text.
            system: Optional system prompt.
            **kwargs: Provider-specific parameters (model, max_tokens, etc.)

        Returns:
            The model's response as a plain string.

        Raises:
            NotImplementedError: If SDK is not installed or key is missing.
        """

    def is_configured(self) -> bool:
        """Return True if an API key has been set."""
        return bool(self.api_key)

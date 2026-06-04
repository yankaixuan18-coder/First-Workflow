"""
Google Gemini provider.
Requires: pip install google-generativeai
"""
from .base import BaseProvider

_SDK_AVAILABLE = False
try:
    import google.generativeai as _genai
    _SDK_AVAILABLE = True
except ImportError:
    pass


class GeminiProvider(BaseProvider):
    provider_name = "gemini"

    def __init__(self, api_key: str = "", **kwargs):
        super().__init__(api_key=api_key, **kwargs)

    def complete(self, prompt: str, system: str = "", **kwargs) -> str:
        if not _SDK_AVAILABLE:
            raise NotImplementedError(
                "The 'google-generativeai' package is not installed. "
                "Run: pip install google-generativeai"
            )
        if not self.api_key:
            raise NotImplementedError(
                "GEMINI_API_KEY is not set. "
                "Add it to your .env file: GEMINI_API_KEY=AIza..."
            )
        _genai.configure(api_key=self.api_key)
        model_name = kwargs.get("model", "gemini-1.5-flash")
        model = _genai.GenerativeModel(
            model_name=model_name,
            system_instruction=system if system else None,
        )
        full_prompt = prompt
        response = model.generate_content(full_prompt)
        return response.text

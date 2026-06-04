"""
Abstract base class for browser extension data adapters.
Each adapter reads data injected into the Amazon page DOM by a specific extension.
"""
from abc import ABC, abstractmethod


class BaseExtensionAdapter(ABC):
    name: str = "base"

    @abstractmethod
    async def extract(self, page, asin: str) -> dict:
        """
        Extract extension-injected data for a given ASIN from the current page.

        Args:
            page: Playwright page object (async context).
            asin: The ASIN of the product on the current page.

        Returns:
            dict of field_name -> value (str). Empty string when not found.
        """

    def empty_data(self) -> dict:
        """Return an empty data dict with all expected keys set to empty string."""
        return {}

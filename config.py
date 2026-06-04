"""
Central configuration for the Amazon category research tool.
"""
import os

MARKETPLACES = {
    "amazon.com": "https://www.amazon.com",
    "amazon.co.uk": "https://www.amazon.co.uk",
    "amazon.de": "https://www.amazon.de",
    "amazon.co.jp": "https://www.amazon.co.jp",
    "amazon.ca": "https://www.amazon.ca",
    "amazon.com.au": "https://www.amazon.com.au",
    "amazon.fr": "https://www.amazon.fr",
    "amazon.es": "https://www.amazon.es",
    "amazon.it": "https://www.amazon.it",
}

DEFAULT_CHROME_USER_DATA_DIR_WINDOWS = r"C:\Users\{username}\AppData\Local\Google\Chrome\User Data"
DEFAULT_CHROME_USER_DATA_DIR_MAC = "~/Library/Application Support/Google/Chrome"
DEFAULT_CHROME_USER_DATA_DIR_LINUX = "~/.config/google-chrome"
DEFAULT_CHROME_PROFILE = "Default"

MAX_PAGES_DEFAULT = 5
MAX_PRODUCTS_DEFAULT = 100

REQUEST_DELAY_MIN = 2.0   # seconds between page loads
REQUEST_DELAY_MAX = 4.0

# Output directory for exported Excel files
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")


def get_default_chrome_user_data_dir() -> str:
    """Return the platform-appropriate default Chrome user data directory."""
    import platform
    system = platform.system()
    if system == "Windows":
        username = os.environ.get("USERNAME", "User")
        return DEFAULT_CHROME_USER_DATA_DIR_WINDOWS.format(username=username)
    elif system == "Darwin":
        return os.path.expanduser(DEFAULT_CHROME_USER_DATA_DIR_MAC)
    else:
        return os.path.expanduser(DEFAULT_CHROME_USER_DATA_DIR_LINUX)

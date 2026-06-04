"""
Playwright Chrome controller with user profile support.
Runs in sync mode so it can be used from background threads.
"""
import os
import random
import time
import logging

logger = logging.getLogger(__name__)


class BrowserController:
    """Controls a persistent Chrome browser context via Playwright."""

    def __init__(self, chrome_user_data_dir: str, chrome_profile: str = "Default", headless: bool = False):
        # Expand environment variables and user home in path
        self.chrome_user_data_dir = os.path.expandvars(os.path.expanduser(chrome_user_data_dir))
        self.chrome_profile = chrome_profile
        # Extensions require headed mode — headless is always False
        self.headless = False
        self._playwright = None
        self._context = None
        self._page = None

    def launch(self):
        """
        Launch a persistent Chrome context using the user's real Chrome profile.
        This allows browser extensions (卖家精灵, SIF, etc.) to be active.

        Raises RuntimeError if the profile is locked (another Chrome instance is running).
        """
        from playwright.sync_api import sync_playwright

        profile_path = self.chrome_user_data_dir

        if not os.path.exists(profile_path):
            raise RuntimeError(
                f"Chrome user data directory not found: {profile_path}\n"
                "Please set CHROME_USER_DATA_DIR in your .env file to the correct path."
            )

        # Check for Chrome lock file — indicates another Chrome process is running
        lock_file = os.path.join(profile_path, "lockfile")
        singleton_lock = os.path.join(profile_path, "SingletonLock")
        for lf in (lock_file, singleton_lock):
            if os.path.exists(lf):
                raise RuntimeError(
                    f"Chrome profile is locked: {lf}\n"
                    "Please close all Chrome windows completely before running this tool.\n"
                    "Tip: Check Task Manager / Activity Monitor for lingering chrome.exe processes."
                )

        logger.info(f"Launching Chrome with profile: {profile_path} [{self.chrome_profile}]")

        self._playwright = sync_playwright().start()

        try:
            self._context = self._playwright.chromium.launch_persistent_context(
                user_data_dir=profile_path,
                channel="chrome",
                headless=False,
                args=[
                    "--start-maximized",
                    f"--profile-directory={self.chrome_profile}",
                    "--disable-blink-features=AutomationControlled",
                    "--no-first-run",
                    "--no-default-browser-check",
                ],
                ignore_default_args=["--enable-automation"],
                viewport=None,  # let --start-maximized control size
            )
        except Exception as exc:
            self._playwright.stop()
            self._playwright = None
            if "Target page, context or browser has been closed" in str(exc):
                raise RuntimeError(
                    "Could not launch Chrome. Ensure Chrome is installed and "
                    "the profile path is correct."
                ) from exc
            if "is already in use" in str(exc) or "profile" in str(exc).lower():
                raise RuntimeError(
                    "Chrome profile is already in use by another process.\n"
                    "Close all Chrome windows and try again."
                ) from exc
            raise RuntimeError(f"Failed to launch Chrome: {exc}") from exc

        # Use the first existing page or open a new one
        if self._context.pages:
            self._page = self._context.pages[0]
        else:
            self._page = self._context.new_page()

        logger.info("Chrome launched successfully.")

    def navigate(self, url: str):
        """Navigate to a URL and wait for network to settle."""
        if self._page is None:
            raise RuntimeError("Browser not launched. Call launch() first.")
        logger.info(f"Navigating to: {url}")
        self._page.goto(url, wait_until="networkidle", timeout=30_000)

    def scroll_to_bottom(self):
        """
        Incrementally scroll to the bottom of the page with random delays
        to trigger lazy-loaded content (images, extension overlays, etc.).
        """
        if self._page is None:
            return
        total_height = self._page.evaluate("document.body.scrollHeight")
        viewport_height = self._page.evaluate("window.innerHeight")
        current_position = 0
        step = viewport_height // 2

        while current_position < total_height:
            current_position = min(current_position + step, total_height)
            self._page.evaluate(f"window.scrollTo(0, {current_position})")
            time.sleep(random.uniform(0.2, 0.5))
            # Recalculate total height in case dynamic content was loaded
            total_height = self._page.evaluate("document.body.scrollHeight")

        # Scroll back to top so the page is in a normal state
        self._page.evaluate("window.scrollTo(0, 0)")
        time.sleep(random.uniform(0.3, 0.6))

    def get_page_html(self) -> str:
        """Return the full HTML content of the current page."""
        if self._page is None:
            raise RuntimeError("Browser not launched.")
        return self._page.content()

    def get_page(self):
        """Return the Playwright page object."""
        return self._page

    def close(self):
        """Close the browser context and stop Playwright."""
        try:
            if self._context is not None:
                self._context.close()
        except Exception as exc:
            logger.warning(f"Error closing browser context: {exc}")
        finally:
            self._context = None
            self._page = None

        try:
            if self._playwright is not None:
                self._playwright.stop()
        except Exception as exc:
            logger.warning(f"Error stopping Playwright: {exc}")
        finally:
            self._playwright = None

        logger.info("Browser closed.")

    def wait(self, min_s: float, max_s: float):
        """Sleep for a random duration between min_s and max_s seconds."""
        duration = random.uniform(min_s, max_s)
        logger.debug(f"Waiting {duration:.1f}s …")
        time.sleep(duration)

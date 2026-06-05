"""
Playwright Microsoft Edge controller with user profile support.
Runs in sync mode so it can be used from background threads.
"""
import os
import random
import time
import logging

logger = logging.getLogger(__name__)


class BrowserController:
    """Controls a persistent Edge browser context via Playwright."""

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
        Launch a persistent Edge context using the user's real Edge profile.
        This allows browser extensions (卖家精灵, SIF, etc.) to be active.

        Raises RuntimeError if the profile is locked (another Edge instance is running).
        """
        from playwright.sync_api import sync_playwright

        profile_path = self.chrome_user_data_dir

        if not os.path.exists(profile_path):
            raise RuntimeError(
                f"Edge user data directory not found: {profile_path}\n"
                "Please set CHROME_USER_DATA_DIR in your .env file to the correct Edge path."
            )

        # Check for Edge lock file — indicates another Edge process is running
        lock_file = os.path.join(profile_path, "lockfile")
        singleton_lock = os.path.join(profile_path, "SingletonLock")
        for lf in (lock_file, singleton_lock):
            if os.path.exists(lf):
                raise RuntimeError(
                    f"Edge profile is locked: {lf}\n"
                    "Please close all Edge windows completely before running this tool.\n"
                    "Tip: Check Task Manager / Activity Monitor for lingering msedge.exe processes."
                )

        logger.info(f"Launching Edge with profile: {profile_path} [{self.chrome_profile}]")

        self._playwright = sync_playwright().start()

        try:
            self._context = self._playwright.chromium.launch_persistent_context(
                user_data_dir=profile_path,
                channel="msedge",
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
                    "Could not launch Edge. Ensure Microsoft Edge is installed and "
                    "the profile path is correct."
                ) from exc
            if "is already in use" in str(exc) or "profile" in str(exc).lower():
                raise RuntimeError(
                    "Edge profile is already in use by another process.\n"
                    "Close all Edge windows and try again."
                ) from exc
            raise RuntimeError(f"Failed to launch Edge: {exc}") from exc

        # Use the first existing page or open a new one
        if self._context.pages:
            self._page = self._context.pages[0]
        else:
            self._page = self._context.new_page()

        # Hide automation fingerprints so extensions (卖家精灵/SIF) and Amazon
        # treat this as a normal browser and inject their data.
        try:
            self._context.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
                "window.chrome = window.chrome || { runtime: {} };"
                "Object.defineProperty(navigator, 'languages', {get: () => ['en-US','en']});"
                "Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});"
            )
        except Exception as exc:
            logger.warning(f"Could not add stealth init script: {exc}")

        logger.info("Edge launched successfully.")

    def navigate(self, url: str):
        """
        Navigate to a URL. Wait for the DOM to load, then give extensions
        and lazy content a moment to render.

        Amazon pages keep background network activity alive (ads, telemetry),
        so "networkidle" never fires. We use "domcontentloaded" and tolerate
        timeouts — the page is usually fully usable well before any timeout.
        """
        if self._page is None:
            raise RuntimeError("Browser not launched. Call launch() first.")
        logger.info(f"Navigating to: {url}")
        try:
            self._page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        except Exception as exc:
            # Page may still have loaded enough to parse — log and continue
            logger.warning(f"Navigation wait timed out, continuing anyway: {exc}")
        # Give the page (and extensions) extra time to render
        try:
            self._page.wait_for_load_state("load", timeout=10_000)
        except Exception:
            pass
        time.sleep(random.uniform(2.0, 3.5))

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

    # Keywords that the 卖家精灵 overlay reliably renders once it has loaded.
    _SS_KEYWORDS = [
        "近30天销量", "月销量", "销售额", "FBA费用",
        "毛利率", "全部流量", "自然搜索词", "广告流量",
    ]

    def wait_for_seller_sprite(
        self,
        timeout_s: float = 20.0,
        settle_s: float = 2.5,
        poll_s: float = 0.5,
    ) -> bool:
        """
        Wait until the SellerSprite (卖家精灵) overlay has injected its data
        into the current page.

        Detection: poll the page body for any known overlay keyword.
        Once detected, sleep `settle_s` extra seconds so every field finishes
        rendering before the adapter reads the DOM.

        Returns True if the overlay was detected, False on timeout
        (extension not installed, not logged in, or still loading).
        """
        if self._page is None:
            return False

        keywords_js = "[" + ",".join(f'"{k}"' for k in self._SS_KEYWORDS) + "]"
        check_js = (
            "() => { const kws = " + keywords_js + "; "
            "const body = document.body ? (document.body.innerText || '') : ''; "
            "return kws.some(kw => body.includes(kw)); }"
        )

        deadline = time.time() + timeout_s
        detected = False
        while time.time() < deadline:
            try:
                if self._page.evaluate(check_js):
                    detected = True
                    break
            except Exception:
                pass
            # Nudge lazy content / extension rendering by a small scroll
            try:
                self._page.evaluate("window.scrollBy(0, 250)")
            except Exception:
                pass
            time.sleep(poll_s)

        if detected:
            # Give the overlay extra time to fully populate every field
            time.sleep(settle_s)
        return detected

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

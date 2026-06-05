"""
Playwright Microsoft Edge controller with user profile support.
Runs in sync mode so it can be used from background threads.

Two launch modes:
  - CDP mode (default): connects to an already-running Edge instance that was
    started with --remote-debugging-port=9222. All existing logins, cookies,
    and extensions (卖家精灵, SIF, etc.) remain active.
  - Persistent context mode (fallback): launches a new Edge window using the
    user's real profile directory.
"""
import os
import random
import time
import logging

logger = logging.getLogger(__name__)

CDP_DEFAULT_URL = "http://127.0.0.1:9222"


class BrowserController:
    """Controls a persistent Edge browser context via Playwright."""

    def __init__(
        self,
        chrome_user_data_dir: str = "",
        chrome_profile: str = "Default",
        headless: bool = False,
        cdp_url: str = CDP_DEFAULT_URL,
        use_cdp: bool = True,
    ):
        self.chrome_user_data_dir = os.path.expandvars(os.path.expanduser(chrome_user_data_dir)) if chrome_user_data_dir else ""
        self.chrome_profile = chrome_profile
        self.headless = False
        self.cdp_url = cdp_url
        self.use_cdp = use_cdp
        self._playwright = None
        self._browser = None   # only set in CDP mode
        self._context = None
        self._page = None
        self._cdp_connected = False

    def launch(self):
        """
        Connect to (CDP mode) or launch (persistent context mode) Edge.

        CDP mode: Edge must already be running with --remote-debugging-port=9222.
        The start.bat script takes care of this automatically.
        """
        if self.use_cdp:
            self._launch_cdp()
        else:
            self._launch_persistent()

    @staticmethod
    def _probe_cdp(http_url: str):
        """
        Hit the CDP /json/version endpoint to confirm the port is live and get
        the real webSocketDebuggerUrl. Returns the ws URL (str) or None.
        Connecting via the ws URL is more reliable than letting Playwright guess,
        and it lets us distinguish "port not ready" from "wrong host".
        """
        import json as _json
        import urllib.request as _req

        try:
            with _req.urlopen(http_url.rstrip("/") + "/json/version", timeout=2) as resp:
                data = _json.loads(resp.read().decode("utf-8"))
            ws = data.get("webSocketDebuggerUrl", "")
            # Normalize the ws host to match the http host we probed (handles
            # the localhost -> 127.0.0.1 case so the ws also uses 127.0.0.1).
            if ws and "127.0.0.1" in http_url:
                ws = ws.replace("localhost", "127.0.0.1")
            return ws or http_url
        except Exception:
            return None

    def _launch_cdp(self):
        """Connect to an existing Edge/Chrome via CDP."""
        from playwright.sync_api import sync_playwright

        # Build the list of candidate URLs to try. On Windows, "localhost" often
        # resolves to IPv6 ::1 while Edge's debug port only listens on IPv4
        # 127.0.0.1 — so always try 127.0.0.1 explicitly as well.
        candidates = []
        for url in (self.cdp_url, self.cdp_url.replace("localhost", "127.0.0.1")):
            if url not in candidates:
                candidates.append(url)

        logger.info(f"Connecting to existing Edge via CDP at {self.cdp_url} …")
        self._playwright = sync_playwright().start()

        last_exc = None
        # Edge may still be opening the port right after launch; retry a few times.
        for attempt in range(6):
            for url in candidates:
                ws = self._probe_cdp(url)
                if not ws:
                    continue
                try:
                    self._browser = self._playwright.chromium.connect_over_cdp(ws)
                    if url != self.cdp_url:
                        logger.info(f"Connected via {url} (localhost fell back to 127.0.0.1).")
                    break
                except Exception as exc:
                    last_exc = exc
            if self._browser:
                break
            time.sleep(1.0)

        if not self._browser:
            self._playwright.stop()
            self._playwright = None
            raise RuntimeError(
                f"Could not connect to Edge at {self.cdp_url}.\n"
                "Run open-edge.bat first to open the tool's dedicated browser window."
            ) from last_exc

        # Reuse the first existing context (preserves all logins and extensions)
        contexts = self._browser.contexts
        if contexts:
            self._context = contexts[0]
        else:
            self._context = self._browser.new_context()

        # Always open a new tab so the app UI (localhost:5000) stays untouched
        self._page = self._context.new_page()

        self._cdp_connected = True
        logger.info("Connected to existing Edge browser via CDP.")

    def _launch_persistent(self):
        """
        Fallback: launch Edge with a dedicated profile stored inside the project
        directory. This runs alongside the user's main Edge (different user-data-dir)
        so there is never a lockfile conflict, regardless of what else is open.
        """
        from playwright.sync_api import sync_playwright

        # Dedicated profile lives next to the project — never conflicts with main Edge.
        project_root = os.path.dirname(os.path.abspath(__file__))
        profile_path = os.path.join(project_root, "browser-profile")
        os.makedirs(profile_path, exist_ok=True)

        logger.info(f"Launching dedicated Edge profile at: {profile_path}")
        self._playwright = sync_playwright().start()

        try:
            self._context = self._playwright.chromium.launch_persistent_context(
                user_data_dir=profile_path,
                channel="msedge",
                headless=False,
                args=[
                    "--start-maximized",
                    "--disable-blink-features=AutomationControlled",
                    "--no-first-run",
                    "--no-default-browser-check",
                ],
                ignore_default_args=["--enable-automation"],
                viewport=None,
            )
        except Exception as exc:
            self._playwright.stop()
            self._playwright = None
            raise RuntimeError(f"Failed to launch Edge: {exc}") from exc

        if self._context.pages:
            self._page = self._context.pages[0]
        else:
            self._page = self._context.new_page()

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
        """
        if self._page is None:
            raise RuntimeError("Browser not launched. Call launch() first.")
        logger.info(f"Navigating to: {url}")
        try:
            self._page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        except Exception as exc:
            logger.warning(f"Navigation wait timed out, continuing anyway: {exc}")
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
            total_height = self._page.evaluate("document.body.scrollHeight")

        self._page.evaluate("window.scrollTo(0, 0)")
        time.sleep(random.uniform(0.3, 0.6))

    def get_page_html(self) -> str:
        """Return the full HTML content of the current page."""
        if self._page is None:
            raise RuntimeError("Browser not launched.")
        return self._page.content()

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
        Wait until the SellerSprite (卖家精灵) overlay has injected its data.
        Returns True if detected, False on timeout.
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
            try:
                self._page.evaluate("window.scrollBy(0, 250)")
            except Exception:
                pass
            time.sleep(poll_s)

        if detected:
            time.sleep(settle_s)
        return detected

    def get_page(self):
        """Return the Playwright page object."""
        return self._page

    def close(self):
        """
        Disconnect from (CDP mode) or close (persistent context mode) the browser.
        In CDP mode the browser stays open — the user owns it.
        """
        if self._cdp_connected:
            # Close only the tab we opened; leave all other tabs and the browser running
            try:
                if self._page is not None:
                    self._page.close()
            except Exception as exc:
                logger.warning(f"Error closing scrape tab: {exc}")
            finally:
                self._page = None
            try:
                if self._playwright is not None:
                    self._playwright.stop()
            except Exception as exc:
                logger.warning(f"Error stopping Playwright: {exc}")
            finally:
                self._playwright = None
                self._browser = None
                self._context = None
            logger.info("Disconnected from Edge (browser left open).")
            return

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

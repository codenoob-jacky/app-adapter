"""
Real Playwright CDP Executor for browser automation.

Optional dependency: playwright
Install: pip install playwright && python -m playwright install chromium

If Playwright is not available, CDP actions fall back to instruction mode
(telling the agent what to do) rather than silent failure.
"""
import asyncio, json, sys
from typing import Optional


class CDPExecutor:
    """Wraps Playwright for real browser automation."""

    def __init__(self):
        self._browser = None
        self._page = None
        self._playwright = None
        self._available = None  # None = not checked yet

    @property
    def available(self) -> bool:
        """Check if Playwright is installed and working."""
        if self._available is not None:
            return self._available
        try:
            from playwright.sync_api import sync_playwright
            self._playwright = sync_playwright
            self._available = True
        except ImportError:
            self._available = False
        return self._available

    def _ensure_browser(self):
        """Lazy-init browser connection."""
        if not self.available:
            return False
        if self._page is None:
            try:
                pw = self._playwright()
                # Try to connect to existing browser first
                try:
                    self._browser = pw.chromium.connect_over_cdp("http://localhost:9222")
                except Exception:
                    self._browser = pw.chromium.launch(headless=False)
                self._page = self._browser.new_page() if not self._browser.contexts else self._browser.contexts[0].new_page()
            except Exception:
                return False
        return True

    def execute(self, cmd: str, action: dict, params: dict) -> str:
        """Execute a CDP command using Playwright."""
        if not self._ensure_browser():
            return self._instruction_mode(cmd, action, params)

        selector = action.get("selector", "")
        text = params.get("text", params.get("content", ""))
        url = params.get("url") or action.get("params", {}).get("url", "")

        try:
            if cmd == "navigate":
                if not url:
                    return "[CDP] No URL provided for navigation."
                self._page.goto(url, wait_until="domcontentloaded", timeout=15000)
                title = self._page.title()
                return f"[CDP ✓] Navigated to {url}\n  Page title: {title}"

            elif cmd == "click":
                if not selector:
                    return "[CDP] No selector provided for click."
                self._page.wait_for_selector(selector, timeout=5000)
                self._page.click(selector)
                return f"[CDP ✓] Clicked '{selector}'"

            elif cmd == "fill":
                if not selector:
                    return "[CDP] No selector provided for fill."
                if not text:
                    return "[CDP] No text provided for fill."
                self._page.wait_for_selector(selector, timeout=5000)
                self._page.fill(selector, text)
                return f"[CDP ✓] Filled '{selector}' with '{text[:100]}'"

            elif cmd == "fill_then_click":
                fill_sel = action.get("fill_selector", selector)
                click_sel = action.get("click_selector", "")
                if fill_sel:
                    self._page.wait_for_selector(fill_sel, timeout=5000)
                    self._page.fill(fill_sel, text)
                if click_sel:
                    self._page.click(click_sel)
                elif fill_sel:
                    self._page.press(fill_sel, "Enter")
                return f"[CDP ✓] Filled '{fill_sel}' and submitted."

            elif cmd == "click_then_upload":
                self._page.click(selector)
                # File upload requires the file chooser
                file_path = params.get("file", params.get("path", ""))
                if file_path:
                    with self._page.expect_file_chooser() as fc_info:
                        self._page.click(selector)
                    file_chooser = fc_info.value
                    file_chooser.set_files(file_path)
                    return f"[CDP ✓] Clicked '{selector}' and uploaded '{file_path}'"
                return f"[CDP ✓] Clicked '{selector}' — select file manually."

            elif cmd == "screenshot":
                path = params.get("path", "screenshot.png")
                self._page.screenshot(path=path, full_page=True)
                return f"[CDP ✓] Screenshot saved to '{path}'"

            elif cmd == "evaluate":
                js = action.get("js", "")
                result = self._page.evaluate(js)
                return f"[CDP ✓] JS result: {str(result)[:2000]}"

            elif cmd == "get_text":
                text_content = self._page.inner_text("body")
                return f"[CDP ✓] Page text:\n{text_content[:3000]}"

            return f"[CDP ✓] Executed {cmd}: {action.get('desc', '')}"

        except Exception as e:
            error_msg = str(e)[:300]
            # Provide actionable hints
            if "net::ERR_" in error_msg:
                return f"[CDP ✗] Network error: {error_msg}\n  Hint: Check the URL and network connection."
            elif "timeout" in error_msg.lower():
                return f"[CDP ✗] Timed out waiting for '{selector}'\n  Hint: The selector may be wrong or the element hasn't loaded. Try a different selector."
            elif "selector" in error_msg.lower():
                return f"[CDP ✗] Selector not found: '{selector}'\n  Hint: Inspect the page to find the correct CSS selector."
            return f"[CDP ✗] {error_msg}"

    def _instruction_mode(self, cmd: str, action: dict, params: dict) -> str:
        """Fallback: tell the agent what to do."""
        selector = action.get("selector", "")
        text = params.get("text", params.get("content", ""))
        url = params.get("url") or action.get("params", {}).get("url", "")

        hints = {
            "navigate": f"Open browser and go to: {url or '(no URL configured)'}",
            "click": f"Find and click element: '{selector}'",
            "fill": f"Type '{text[:100]}' into: '{selector}'",
            "fill_then_click": f"Fill the form field, then click submit",
            "click_then_upload": f"Click '{selector}', then select file to upload",
            "screenshot": "Take a screenshot of the current page",
            "evaluate": f"Run in console: {action.get('js', '')[:200]}",
            "get_text": "Extract all text content from the page",
        }

        instruction = hints.get(cmd, f"Execute CDP command: {cmd}")
        return f"[CDP] {instruction}\n  Install Playwright for real automation: pip install playwright && python -m playwright install chromium"


# Singleton
_cdp_executor: Optional[CDPExecutor] = None


def get_cdp_executor() -> CDPExecutor:
    global _cdp_executor
    if _cdp_executor is None:
        _cdp_executor = CDPExecutor()
    return _cdp_executor

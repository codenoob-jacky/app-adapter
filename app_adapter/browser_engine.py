"""
Browser engine — a persistent dedicated browser controlled via CDP.

Design (proven in production by voice_agent's core/playwright_browser.py):
- Launches a real browser as a DETACHED process with a dedicated profile.
  The browser survives Python exits, so logins and cookies persist across runs.
- Connects via Playwright connect_over_cdp — no bundled chromium download needed.
- Singleton page: every get_page() call validates the cached page with a real
  CDP round-trip and reconnects if the tab was closed or the browser died.

Config (environment variables):
  APP_ADAPTER_CDP_PORT         debug port    (default 9225; voice_agent uses 9224)
  APP_ADAPTER_BROWSER_PROFILE  profile dir  (default ~/.app-adapter/browser_profile)
  APP_ADAPTER_BROWSER_CMD      browser exe  (default: auto-detect Edge/Chrome/Chromium)
"""
import os
import shutil
import subprocess
import threading
import time
from urllib.request import Request, urlopen

_page = None
_playwright = None
_browser = None
_lock = threading.Lock()

# Windows absolute paths first (Edge ships with Windows), then PATH names.
_BROWSER_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    "msedge", "msedge.exe",
    "google-chrome", "chrome", "chromium", "chromium-browser",
]


def config() -> dict:
    """Current engine configuration (env-overridable, read at call time)."""
    return {
        "port": int(os.environ.get("APP_ADAPTER_CDP_PORT", "9225")),
        "profile": os.path.expanduser(
            os.environ.get("APP_ADAPTER_BROWSER_PROFILE", "~/.app-adapter/browser_profile")
        ),
        "browser_cmd": os.environ.get("APP_ADAPTER_BROWSER_CMD", "").strip(),
    }


def find_browser() -> str:
    """Locate a Chromium-based browser executable. Empty string = not found."""
    cfg = config()
    if cfg["browser_cmd"]:
        expanded = os.path.expanduser(cfg["browser_cmd"])
        if os.path.isfile(expanded):
            return expanded
        hit = shutil.which(expanded)
        return hit or ""
    for candidate in _BROWSER_CANDIDATES:
        expanded = os.path.expandvars(candidate)
        if os.path.isfile(expanded):
            return expanded
        hit = shutil.which(candidate)
        if hit:
            return hit
    return ""


def _is_alive(port: int) -> bool:
    """Check if the debug browser is running on the port."""
    try:
        req = Request(f"http://127.0.0.1:{port}/json/version", headers={})
        with urlopen(req, timeout=1) as resp:
            return True
    except Exception:
        return False


def _launch() -> None:
    """Launch the browser as an independent process with the debug port."""
    cfg = config()
    browser = find_browser()
    if not browser:
        raise RuntimeError(
            "No Chromium-based browser found (tried Edge/Chrome/Chromium). "
            "Fix: set APP_ADAPTER_BROWSER_CMD to your browser executable path."
        )

    os.makedirs(cfg["profile"], exist_ok=True)
    subprocess.Popen(
        [
            browser,
            f"--remote-debugging-port={cfg['port']}",
            "--remote-allow-origins=*",
            f"--user-data-dir={cfg['profile']}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-blink-features=AutomationControlled",
            "--disable-features=IsolateOrigins,site-per-process",
            "--disable-site-isolation-trials",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        # Detach from parent — browser survives Python exit
        creationflags=subprocess.DETACHED_PROCESS if hasattr(subprocess, "DETACHED_PROCESS") else 0,
    )

    deadline = time.time() + 15
    while time.time() < deadline:
        if _is_alive(cfg["port"]):
            return
        time.sleep(0.5)
    raise RuntimeError(
        f"Browser started but debug port {cfg['port']} never came up. "
        "Hint: another browser instance may own the profile — close it or set "
        "APP_ADAPTER_BROWSER_PROFILE to a fresh directory."
    )


def _pick_best_page(pages):
    """Pick the best page to use — skip devtools:// and browser:// pages."""
    for p in pages:
        try:
            if p.url and not p.url.startswith(("devtools://", "edge://", "chrome://")):
                return p
        except Exception:
            pass
    return pages[0] if pages else None


def get_page():
    """Get or create the Playwright page connected to the persistent browser.

    Always validates the cached page with a real CDP call. If the page is stale
    (tab closed, context detached, browser killed), reconnects from scratch.
    """
    global _page, _playwright, _browser
    cfg = config()

    with _lock:
        # ── Validate cached page ──
        if _page is not None:
            try:
                closed = _page.is_closed()
            except Exception:
                closed = True
            if not closed:
                try:
                    _page.evaluate("1")  # real CDP call — catches stale pages
                    url = _page.url
                    if url and not url.startswith(("devtools://", "edge://", "chrome://")):
                        return _page
                except Exception:
                    pass  # evaluate failed → page is stale
            _page = None

        # ── Ensure browser is running ──
        if not _is_alive(cfg["port"]):
            _launch()
            time.sleep(1)

        from playwright.sync_api import sync_playwright

        # ── Reconnect (or first connect) ──
        if _playwright is None:
            _playwright = sync_playwright().start()
        else:
            # Existing playwright instance may have a stale browser ref
            try:
                if _browser is not None and _browser.is_connected():
                    contexts = _browser.contexts
                    if contexts:
                        pages = [p for p in contexts[0].pages if not p.is_closed()]
                        best = _pick_best_page(pages)
                        if best:
                            _page = best
                            _page.evaluate("1")  # validate
                            return _page
            except Exception:
                _browser = None

        _browser = _playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{cfg['port']}")

        contexts = _browser.contexts
        context = contexts[0] if contexts else _browser.new_context()
        pages = [p for p in context.pages if not p.is_closed()]
        best = _pick_best_page(pages)
        _page = best if best else (pages[0] if pages else context.new_page())
        return _page


def close():
    """Drop the connection (the browser itself keeps running — by design)."""
    global _playwright, _browser, _page
    with _lock:
        try:
            if _playwright:
                _playwright.stop()
        except Exception:
            pass
        _playwright = None
        _browser = None
        _page = None

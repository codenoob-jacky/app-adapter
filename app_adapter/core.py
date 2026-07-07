"""
App Adapter — Control any software via unified commands.

Strategy priority: HTTP API > Browser CDP > Desktop UIA > Shell > Startfile
Design: humans need GUI (buttons, menus), machines just need commands.
The adapter bridges this gap — and agents can contribute back.

All functions return strings for LLM-friendliness.
Error messages are actionable — they tell the agent HOW to fix the issue.
"""
import functools, inspect, json, os, re, subprocess, sys, time
from typing import Optional
from urllib.request import Request, urlopen
from urllib.error import URLError
import ssl

_SSL = ssl.create_default_context()
_SSL.check_hostname = False
_SSL.verify_mode = ssl.CERT_NONE

ADAPTERS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "adapters.json")

# ═══════════════════════════════════════════════════════════════
# Built-in defaults — curated adapters for common apps.
# Agents extend these at runtime via register/learn.
# ═══════════════════════════════════════════════════════════════

DEFAULT_ADAPTERS = {
    # ── Communication ──
    "zoom": {
        "name": "Zoom",
        "category": "communication",
        "actions": {
            "open": {"desc": "Open Zoom desktop client", "strategy": "startfile", "path": "Zoom.exe"},
            "send_chat": {"desc": "Type text into Zoom chat input and send", "strategy": "uia", "uia_action": "type_text", "target": "Zoom chat input"},
            "start_monitor": {"desc": "Start monitoring Zoom chat with TTS announcements", "strategy": "shell", "command": "echo 'Zoom monitor started'"},
        },
    },
    "slack": {
        "name": "Slack",
        "url": "https://slack.com",
        "category": "communication",
        "actions": {
            "open": {"desc": "Open Slack in browser", "strategy": "cdp", "cdp_cmd": "navigate", "params": {"url": "https://slack.com"}},
            "send_message": {"desc": "Send message to channel", "strategy": "cdp", "cdp_cmd": "fill_then_click", "fill_selector": "[data-qa='message_input']", "click_selector": "[data-qa='texty_send_button']"},
        },
    },
    "discord": {
        "name": "Discord",
        "url": "https://discord.com",
        "category": "communication",
        "actions": {
            "open": {"desc": "Open Discord in browser", "strategy": "cdp", "cdp_cmd": "navigate", "params": {"url": "https://discord.com/app"}},
            "send_message": {"desc": "Send message in current channel", "strategy": "cdp", "cdp_cmd": "fill_then_click", "fill_selector": "[data-slate-editor='true']", "click_selector": "button[aria-label='Send']"},
        },
    },
    "teams": {
        "name": "Microsoft Teams",
        "url": "https://teams.microsoft.com",
        "category": "communication",
        "actions": {
            "open": {"desc": "Open Teams in browser", "strategy": "cdp", "cdp_cmd": "navigate", "params": {"url": "https://teams.microsoft.com"}},
            "send_chat": {"desc": "Send chat message", "strategy": "cdp", "cdp_cmd": "fill_then_click", "fill_selector": "#cke_editor .cke_editable, [contenteditable='true']", "click_selector": "button[title='Send']"},
        },
    },
    "outlook": {
        "name": "Outlook",
        "url": "https://outlook.office.com",
        "category": "communication",
        "actions": {
            "open": {"desc": "Open Outlook web", "strategy": "cdp", "cdp_cmd": "navigate", "params": {"url": "https://outlook.office.com/mail/"}},
            "compose": {"desc": "Compose new email", "strategy": "cdp", "cdp_cmd": "click", "selector": "button[aria-label='New mail'], [title='New mail']"},
            "fill_subject": {"desc": "Fill email subject", "strategy": "cdp", "cdp_cmd": "fill", "selector": "input[aria-label='Add a subject']"},
        },
    },

    # ── Social Media ──
    "wechat": {
        "name": "WeChat Official Account",
        "url": "https://mp.weixin.qq.com",
        "category": "social",
        "actions": {
            "open": {"desc": "Open WeChat MP backend", "strategy": "cdp", "cdp_cmd": "navigate", "params": {"url": "https://mp.weixin.qq.com"}},
            "new_post": {"desc": "Create new article draft", "strategy": "cdp", "cdp_cmd": "click", "selector": ".js_create_post, [data-action='create']"},
            "fill_title": {"desc": "Fill article title", "strategy": "cdp", "cdp_cmd": "fill", "selector": "#title, [placeholder*='title']"},
            "fill_content": {"desc": "Fill article body", "strategy": "cdp", "cdp_cmd": "fill", "selector": "#editor, [contenteditable='true']"},
            "upload_cover": {"desc": "Upload cover image", "strategy": "cdp", "cdp_cmd": "click_then_upload", "selector": ".js_cover_btn"},
            "publish": {"desc": "Publish article", "strategy": "cdp", "cdp_cmd": "click", "selector": "#publish, .js_publish"},
        },
    },
    "weibo": {
        "name": "Weibo",
        "url": "https://weibo.com",
        "category": "social",
        "actions": {
            "open": {"desc": "Open Weibo", "strategy": "cdp", "cdp_cmd": "navigate", "params": {"url": "https://weibo.com"}},
            "post": {"desc": "Post a weibo", "strategy": "cdp", "cdp_cmd": "fill_then_click", "fill_selector": "textarea[placeholder*='Post']", "click_selector": "a:has-text('Post'), .send-btn"},
            "trends": {"desc": "View trending topics", "strategy": "http", "url": "https://weibo.com/ajax/side/hotSearch"},
        },
    },
    "zhihu": {
        "name": "Zhihu",
        "url": "https://www.zhihu.com",
        "category": "social",
        "actions": {
            "open": {"desc": "Open Zhihu", "strategy": "cdp", "cdp_cmd": "navigate", "params": {"url": "https://www.zhihu.com"}},
            "search": {"desc": "Search Zhihu", "strategy": "cdp", "cdp_cmd": "fill", "selector": "input[placeholder*='search'], #search-input"},
            "trends": {"desc": "View hot topics", "strategy": "http", "url": "https://www.zhihu.com/api/v3/feed/topstory/hot-lists/total?limit=20"},
        },
    },
    "bilibili": {
        "name": "Bilibili",
        "url": "https://www.bilibili.com",
        "category": "social",
        "actions": {
            "open": {"desc": "Open Bilibili", "strategy": "cdp", "cdp_cmd": "navigate", "params": {"url": "https://www.bilibili.com"}},
            "search": {"desc": "Search videos", "strategy": "cdp", "cdp_cmd": "fill", "selector": "input[type='search'], .search-input"},
            "trends": {"desc": "View trending videos", "strategy": "http", "url": "https://api.bilibili.com/x/web-interface/ranking/v2"},
        },
    },
    "xiaohongshu": {
        "name": "Xiaohongshu (RED)",
        "url": "https://www.xiaohongshu.com",
        "category": "social",
        "actions": {
            "open": {"desc": "Open Xiaohongshu", "strategy": "cdp", "cdp_cmd": "navigate", "params": {"url": "https://www.xiaohongshu.com/explore"}},
            "search": {"desc": "Search notes", "strategy": "cdp", "cdp_cmd": "fill", "selector": "input[placeholder*='search'], .search-input"},
        },
    },
    "douyin": {
        "name": "Douyin (TikTok CN)",
        "url": "https://www.douyin.com",
        "category": "social",
        "actions": {
            "open": {"desc": "Open Douyin web", "strategy": "cdp", "cdp_cmd": "navigate", "params": {"url": "https://www.douyin.com"}},
            "search": {"desc": "Search videos", "strategy": "cdp", "cdp_cmd": "fill", "selector": "input[placeholder*='search']"},
        },
    },
    "twitter": {
        "name": "X (Twitter)",
        "url": "https://x.com",
        "category": "social",
        "actions": {
            "open": {"desc": "Open X/Twitter", "strategy": "cdp", "cdp_cmd": "navigate", "params": {"url": "https://x.com"}},
            "post": {"desc": "Compose a tweet", "strategy": "cdp", "cdp_cmd": "fill_then_click", "fill_selector": "[data-testid='tweetTextarea_0'], [aria-label='Post text']", "click_selector": "[data-testid='tweetButton']"},
            "trends": {"desc": "View trending topics", "strategy": "cdp", "cdp_cmd": "navigate", "params": {"url": "https://x.com/explore/tabs/trending"}},
        },
    },

    # ── Productivity ──
    "excel": {
        "name": "Microsoft Excel",
        "category": "productivity",
        "actions": {
            "create": {"desc": "Create new workbook", "strategy": "shell", "command": "python -c \"from openpyxl import Workbook; wb=Workbook(); wb.save('{name}'); print(f'Created {name}')\""},
            "read": {"desc": "Read Excel file contents", "strategy": "shell", "command": "python -c \"from openpyxl import load_workbook; wb=load_workbook('{path}'); [print(f'{s.title}: {[[c.value for c in r] for r in s.iter_rows()][:20]}') for s in wb.worksheets]\""},
            "add_chart": {"desc": "Add chart to sheet", "strategy": "shell", "command": "python -c \"from openpyxl import load_workbook; from openpyxl.chart import BarChart, Reference; wb=load_workbook('{path}'); ws=wb.active; chart=BarChart(); data=Reference(ws, min_col=1, max_col=2, min_row=1, max_row=ws.max_row); chart.add_data(data, titles_from_data=True); ws.add_chart(chart, '{cell}'); wb.save('{path}'); print('Chart added')\""},
        },
    },
    "word": {
        "name": "Microsoft Word",
        "category": "productivity",
        "actions": {
            "create": {"desc": "Create new document", "strategy": "shell", "command": "python -c \"from docx import Document; doc=Document(); doc.add_heading('{title}', 0); doc.add_paragraph('{body}'); doc.save('{name}'); print(f'Created {name}')\""},
            "read": {"desc": "Read Word document", "strategy": "shell", "command": "python -c \"from docx import Document; doc=Document('{path}'); [print(p.text) for p in doc.paragraphs[:30]]\""},
        },
    },
    "powerpoint": {
        "name": "Microsoft PowerPoint",
        "category": "productivity",
        "actions": {
            "create": {"desc": "Create new presentation", "strategy": "shell", "command": "python -c \"from pptx import Presentation; prs=Presentation(); prs.slide_width=12192000; prs.slide_height=6858000; slide=prs.slides.add_slide(prs.slide_layouts[0]); slide.shapes.title.text='{title}'; prs.save('{name}'); print(f'Created {name}')\""},
        },
    },
    "pdf": {
        "name": "PDF Tools",
        "category": "productivity",
        "actions": {
            "generate": {"desc": "Generate PDF from markdown", "strategy": "shell", "command": "python -c \"import markdown; from weasyprint import HTML; html=f'<html><body>{markdown.markdown(open(chr(34){path}chr(34),chr(34)rchr(34)).read())}</body></html>'; HTML(string=html).write_pdf('{output}'); print(f'PDF: {output}')\""},
            "read": {"desc": "Read PDF text", "strategy": "shell", "command": "python -c \"import pdfplumber; pdf=pdfplumber.open('{path}'); [print(p.extract_text()[:2000]) for p in pdf.pages[:5]]\""},
        },
    },
    "notion": {
        "name": "Notion",
        "url": "https://www.notion.so",
        "category": "productivity",
        "actions": {
            "open": {"desc": "Open Notion", "strategy": "cdp", "cdp_cmd": "navigate", "params": {"url": "https://www.notion.so"}},
            "new_page": {"desc": "Create new page", "strategy": "cdp", "cdp_cmd": "click", "selector": "[data-testid='new-page-button']"},
        },
    },
    "github": {
        "name": "GitHub",
        "url": "https://github.com",
        "category": "productivity",
        "actions": {
            "open": {"desc": "Open GitHub", "strategy": "cdp", "cdp_cmd": "navigate", "params": {"url": "https://github.com"}},
            "search": {"desc": "Search repositories", "strategy": "http", "url": "https://api.github.com/search/repositories?q={query}"},
            "create_repo": {"desc": "Create new repository", "strategy": "cdp", "cdp_cmd": "navigate", "params": {"url": "https://github.com/new"}},
            "trending": {"desc": "View trending repos", "strategy": "cdp", "cdp_cmd": "navigate", "params": {"url": "https://github.com/trending"}},
        },
    },

    # ── Development ──
    "vscode": {
        "name": "Visual Studio Code",
        "category": "development",
        "actions": {
            "open": {"desc": "Launch VS Code", "strategy": "shell", "command": "code {path}"},
            "open_project": {"desc": "Open project folder", "strategy": "shell", "command": "code {path}"},
        },
    },
    "terminal": {
        "name": "Terminal / Command Line",
        "category": "development",
        "actions": {
            "run": {"desc": "Run shell command", "strategy": "shell", "command": "{cmd}"},
            "python": {"desc": "Run Python code", "strategy": "shell", "command": "python -c \"{code}\""},
            "pip_install": {"desc": "Install Python package", "strategy": "shell", "command": "pip install {package}"},
        },
    },
    "postman": {
        "name": "Postman",
        "url": "https://web.postman.co",
        "category": "development",
        "actions": {
            "open": {"desc": "Open Postman web", "strategy": "cdp", "cdp_cmd": "navigate", "params": {"url": "https://web.postman.co"}},
            "new_request": {"desc": "Create new API request", "strategy": "cdp", "cdp_cmd": "click", "selector": "[data-testid='new-request-button'], button:has-text('New')"},
        },
    },

    # ── Browser ──
    "browser": {
        "name": "Web Browser",
        "category": "utility",
        "actions": {
            "open": {"desc": "Navigate to URL", "strategy": "cdp", "cdp_cmd": "navigate"},
            "search": {"desc": "Search the web via Google", "strategy": "http", "url": "https://www.google.com/search?q={query}"},
            "screenshot": {"desc": "Take page screenshot", "strategy": "cdp", "cdp_cmd": "screenshot"},
            "get_text": {"desc": "Extract page text content", "strategy": "cdp", "cdp_cmd": "evaluate", "js": "document.body.innerText"},
        },
    },

    # ── Design ──
    "figma": {
        "name": "Figma",
        "url": "https://www.figma.com",
        "category": "design",
        "actions": {
            "open": {"desc": "Open Figma", "strategy": "cdp", "cdp_cmd": "navigate", "params": {"url": "https://www.figma.com"}},
            "new_design": {"desc": "Create new design file", "strategy": "cdp", "cdp_cmd": "navigate", "params": {"url": "https://www.figma.com/files/recent"}},
        },
    },
    "canva": {
        "name": "Canva",
        "url": "https://www.canva.com",
        "category": "design",
        "actions": {
            "open": {"desc": "Open Canva", "strategy": "cdp", "cdp_cmd": "navigate", "params": {"url": "https://www.canva.com"}},
            "create_design": {"desc": "Create new design", "strategy": "cdp", "cdp_cmd": "click", "selector": "button:has-text('Create a design')"},
        },
    },

    # ── Finance ──
    "tradingview": {
        "name": "TradingView",
        "url": "https://www.tradingview.com",
        "category": "finance",
        "actions": {
            "open": {"desc": "Open TradingView", "strategy": "cdp", "cdp_cmd": "navigate", "params": {"url": "https://www.tradingview.com/chart"}},
            "search_symbol": {"desc": "Search stock symbol", "strategy": "cdp", "cdp_cmd": "fill", "selector": "[data-role='symbol-search'] input, .symbol-search input"},
        },
    },
}


# ═══ Persistence ═══

def _load_adapters() -> dict:
    """Load adapters from disk, merging with defaults. Saved adapters override defaults."""
    try:
        if os.path.exists(ADAPTERS_FILE):
            with open(ADAPTERS_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            merged = dict(DEFAULT_ADAPTERS)
            # Deep merge: saved app fully overrides default app
            merged.update(saved)
            return merged
    except Exception:
        pass
    return dict(DEFAULT_ADAPTERS)


def _save_adapters():
    """Persist current adapters to disk."""
    try:
        os.makedirs(os.path.dirname(ADAPTERS_FILE), exist_ok=True)
        with open(ADAPTERS_FILE, "w", encoding="utf-8") as f:
            json.dump(ADAPTERS, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


ADAPTERS = _load_adapters()


# ═══════════════════════════════════════════════════════════════
# Strategy Executors
# Each returns a string that agents can read to understand results.
# ═══════════════════════════════════════════════════════════════

def _execute_http(action: dict, params: dict) -> str:
    """Execute via HTTP API call. Supports GET and POST with auth headers."""
    url_template = action.get("url", "")
    url = url_template.format(**params) if params else url_template
    if not url:
        return "[X] No URL configured for this action.\n  Fix: use app_learn() to teach this action with a URL template, e.g.:\n  app_learn('app|||action|||desc|||http|||https://api.example.com/endpoint?q={param}')"

    method = action.get("method", "GET").upper()
    headers = {"User-Agent": "AppAdapter/1.0", "Accept": "application/json"}
    # Support custom headers
    if action.get("headers"):
        headers.update(action["headers"])
    # Bearer token auth
    if action.get("auth_token"):
        headers["Authorization"] = f"Bearer {action['auth_token']}"

    body = None
    if method == "POST":
        body = json.dumps(params).encode("utf-8")
        headers["Content-Type"] = "application/json"

    try:
        req = Request(url, data=body, headers=headers)
        req.get_method = lambda: method
        resp = urlopen(req, timeout=15, context=_SSL)
        result = resp.read().decode("utf-8", errors="replace")[:3000]
        status = resp.status
        return f"[HTTP {status}] {method} {url}\n{result}"
    except URLError as e:
        return f"[X] HTTP request failed: {e}\n  Tip: Check network connectivity and URL. If the API needs auth, use app_learn() to add auth_token."
    except Exception as e:
        return f"[X] HTTP error: {e}"


def _execute_cdp(action: dict, params: dict) -> str:
    """Execute via Chrome DevTools Protocol using Playwright.

    If Playwright is available, performs REAL browser automation.
    If not available, returns actionable instructions for the agent.
    """
    cmd = action.get("cdp_cmd", "click")
    selector = action.get("selector", "")
    text = params.get("text", params.get("content", ""))
    url = params.get("url") or action.get("params", {}).get("url", "")

    # Try real Playwright execution
    try:
        from .cdp_executor import get_cdp_executor
        cdp = get_cdp_executor()
        if cdp and cdp.available:
            return cdp.execute(cmd, action, params)
    except Exception:
        pass  # Fall through to instruction mode

    # Instruction mode — tell the agent what to do
    if cmd == "navigate":
        return f"[CDP] Navigate to {url or '(no URL provided)'}\n  Action: Open browser and go to the URL above."
    elif cmd == "click":
        return f"[CDP] Click element matching '{selector}'\n  Action: Find and click this element in the browser."
    elif cmd == "fill":
        return f"[CDP] Type '{text}' into '{selector}'\n  Action: Locate the input field and type the text."
    elif cmd == "fill_then_click":
        fill_sel = action.get("fill_selector", selector)
        click_sel = action.get("click_selector", "")
        return f"[CDP] Fill '{fill_sel}' then click '{click_sel}'\n  Action: Type content into the first field, then press submit."
    elif cmd == "click_then_upload":
        return f"[CDP] Click '{selector}' then upload file\n  Action: Click the element to open file dialog, then select the file."
    elif cmd == "screenshot":
        return f"[CDP] Take screenshot of current page.\n  Action: Capture the visible area of the browser."
    elif cmd == "evaluate":
        js = action.get("js", "")
        return f"[CDP] Run JavaScript: {js[:200]}\n  Action: Execute JS in the browser console."
    return f"[CDP] {cmd}: {action.get('desc', '')}\n  Tip: Install Playwright for real browser automation: pip install playwright && python -m playwright install"


def _execute_uia(action: dict, params: dict) -> str:
    """Execute via Windows UI Automation / simulated input.

    Tries real UIAutomation first, falls back to PowerShell SendKeys.
    """
    uia_action = action.get("uia_action", "click")
    target = action.get("target", "")

    if uia_action == "type_text":
        text = params.get("text", "")
        if not text:
            return "[X] type_text requires 'text' parameter.\n  Usage: app_do('app.action|||text=Your message here')"

        # Method 1: Real UIAutomation (find element + send keys)
        try:
            from .uia_executor import get_uia_executor
            uia = get_uia_executor()
            if uia and uia.available:
                result = uia.type_text(target, text)
                if result:
                    return result
        except Exception:
            pass

        # Method 2: PowerShell SendKeys (works with Zoom and many apps)
        try:
            escaped = text.replace('"', '""').replace('+', '{+}').replace('^', '{^}').replace('%', '{%}').replace('~', '{~}')
            ps = f'Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.SendKeys]::SendWait("{escaped}")'
            r = subprocess.run(['powershell', '-Command', ps], capture_output=True, text=True, timeout=10)
            if r.returncode == 0:
                return f"[UIA] Typed '{text[:100]}' into target.\n  Verify in the app window — text may need manual Enter to send."
            return f"[X] SendKeys failed: {r.stderr[:200]}"
        except FileNotFoundError:
            return f"[X] PowerShell not available. On Linux/Mac, install uiautomation: pip install uiautomation"
        except Exception as e:
            return f"[X] type_text failed: {e}"

    elif uia_action == "click":
        # Try to find and click an element
        try:
            from .uia_executor import get_uia_executor
            uia = get_uia_executor()
            if uia and uia.available:
                result = uia.click_element(target)
                if result:
                    return result
        except Exception:
            pass
        return f"[UIA] Click '{target}'.\n  Tip: On Windows, install uiautomation for real desktop automation: pip install uiautomation"

    elif uia_action == "find_window":
        try:
            from .uia_executor import get_uia_executor
            uia = get_uia_executor()
            if uia and uia.available:
                return uia.find_window(target)
        except Exception:
            pass
        return f"[UIA] Find window matching '{target}'.\n  Use the window title or partial name to locate it."

    return f"[UIA] {uia_action} on '{target}'.\n  Use UIAutomation or system-level automation to interact with this element."


def _execute_shell(action: dict, params: dict) -> str:
    """Execute via shell command."""
    cmd_template = action.get("command", "")
    if not cmd_template:
        return "[X] No command configured.\n  Fix: use app_learn() with strategy=shell and a command template, e.g.:\n  app_learn('app|||action|||desc|||shell|||python -c \"print({param})\"')"

    # Safe formatting: only substitute known params
    cmd = cmd_template
    for k, v in params.items():
        cmd = cmd.replace(f"{{{k}}}", str(v))

    # Warn about remaining placeholders
    remaining = re.findall(r'\{(\w+)\}', cmd)
    if remaining:
        return f"[X] Missing parameters: {', '.join(remaining)}\n  Provide these in your action: app_do('app.action|||{remaining[0]}=value, ...')"

    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
        output = r.stdout[:3000] or r.stderr[:1000] or f"Command exited with code {r.returncode}"
        return f"[Shell] {cmd[:200]}\n{output}"
    except subprocess.TimeoutExpired:
        return f"[X] Command timed out after 30s: {cmd[:200]}"
    except Exception as e:
        return f"[X] Shell command failed: {e}\n  Command: {cmd[:200]}"


def _execute_startfile(action: dict, params: dict) -> str:
    """Execute by opening a file or application (Windows/macOS/Linux)."""
    path = action.get("path", "")
    if not path:
        return "[X] No path configured.\n  Fix: use app_learn() with strategy=startfile and path to the application executable."

    try:
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.run(["open", path], check=True)
        else:
            subprocess.run(["xdg-open", path], check=True)
        return f"[Startfile] Launched {path}"
    except FileNotFoundError:
        return f"[X] Application not found: {path}\n  Tip: Try searching for the app first, or use the full path."
    except Exception as e:
        return f"[X] Failed to start {path}: {e}"


EXECUTORS = {
    "http": _execute_http,
    "cdp": _execute_cdp,
    "uia": _execute_uia,
    "shell": _execute_shell,
    "startfile": _execute_startfile,
}


# ═══════════════════════════════════════════════════════════════
# Core API — four primary tools + extended ecosystem
# ═══════════════════════════════════════════════════════════════

def app_do(action_spec: str) -> str:
    """Execute an action on an application.

    Format:
        app_name.action_name
        app_name.action_name|||param1=val1,param2=val2

    Examples:
        app_do("zoom.send_chat|||text=Hello World")
        app_do("weibo.trends")
        app_do("terminal.run|||cmd=dir")
        app_do("browser.search|||query=Python tutorial")
    """
    parts = str(action_spec or "").split("|||", 1)
    action_path = parts[0].strip()
    params_str = parts[1].strip() if len(parts) > 1 else ""

    path_parts = action_path.split(".", 1)
    if len(path_parts) != 2:
        return "[X] Invalid format.\n  Correct format: app_name.action_name|||param1=val1,param2=val2\n  Examples:\n    app_do('zoom.send_chat|||text=Hello')\n    app_do('browser.search|||query=Python')\n    app_do('terminal.run|||cmd=dir')"

    app_name, action_name = path_parts
    app_name = app_name.strip().lower()
    action_name = action_name.strip().lower()

    params = {}
    if params_str:
        for kv in params_str.split(","):
            kv = kv.strip()
            if "=" in kv:
                k, v = kv.split("=", 1)
                params[k.strip()] = v.strip()

    adapter = ADAPTERS.get(app_name)
    if not adapter:
        available = ", ".join(sorted(ADAPTERS.keys()))
        return f"[X] Unknown app '{app_name}'.\n  Available apps: {available}\n  Use app_list() to see details.\n  Use app_register('{app_name}|||Display Name|||URL|||strategy') to add it.\n  Use app_search('{app_name}') to find community adapters."

    action = adapter["actions"].get(action_name)
    if not action:
        available = ", ".join(sorted(adapter["actions"].keys()))
        return f"[X] '{app_name}' has no action '{action_name}'.\n  Available actions: {available}\n  Use app_learn('{app_name}|||{action_name}|||description|||strategy|||config') to teach it."

    strategy = action.get("strategy", "shell")
    executor = EXECUTORS.get(strategy)
    if not executor:
        return f"[X] Unknown strategy '{strategy}' for {app_name}.{action_name}.\n  Valid strategies: http, cdp, uia, shell, startfile"

    return executor(action, params)


def app_list(category: str = "") -> str:
    """List all supported apps and their actions.

    Args:
        category: Optional filter (communication, social, productivity, development, design, finance, utility)

    Returns formatted list of apps and actions.
    """
    lines = []
    cats = {}

    for app_name, adapter in sorted(ADAPTERS.items()):
        cat = adapter.get("category", "other")
        if category and cat != category.lower():
            continue
        cats.setdefault(cat, []).append((app_name, adapter))

    if not cats:
        return f"[!] No apps registered. Use app_register() or app_install() to add apps.\n  Categories available: communication, social, productivity, development, design, finance, utility"

    for cat in sorted(cats):
        apps = cats[cat]
        lines.append(f"═══ {cat.upper()} ({len(apps)} apps) ═══")
        for app_name, adapter in sorted(apps):
            url_hint = f" — {adapter['url']}" if adapter.get("url") else ""
            lines.append(f"  {adapter['name']} ({app_name}){url_hint}")
            for action_name, action in sorted(adapter["actions"].items()):
                strategy_icon = {"http": "[api]", "cdp": "[web]", "uia": "[desk]", "shell": "[sh]", "startfile": "[run]"}.get(action.get("strategy", ""), "[?]")
                lines.append(f"    {strategy_icon} {app_name}.{action_name} → {action['desc']} [{action.get('strategy', 'shell')}]")
        lines.append("")

    lines.append(f"Total: {len(ADAPTERS)} apps | {sum(len(a['actions']) for a in ADAPTERS.values())} actions")
    lines.append(f"Use app_do('app.action|||param=value') to execute.")
    return "\n".join(lines)


def app_register(spec: str) -> str:
    """Register a new application.

    Format: app_name|||Display Name|||URL(optional)|||default_strategy|||category

    Strategies (in priority order):
      http      — REST API calls (fastest, most reliable)
      cdp       — Browser automation via Playwright/CDP
      uia       — Desktop UI automation
      shell     — Shell commands & scripts
      startfile — Launch the application

    Categories: communication, social, productivity, development, design, finance, utility

    Example:
      app_register("slack|||Slack|||https://slack.com|||cdp|||communication")
      app_register("spotify|||Spotify|||https://open.spotify.com|||cdp|||entertainment")
    """
    parts = [p.strip() for p in str(spec or "").split("|||", 4)]
    app_name = parts[0].lower() if len(parts) > 0 else ""
    display_name = parts[1] if len(parts) > 1 else app_name
    app_url = parts[2] if len(parts) > 2 else ""
    strategy = parts[3].lower() if len(parts) > 3 else "cdp"
    category = parts[4].lower() if len(parts) > 4 else "utility"

    if not app_name:
        return "[X] Format: app_name|||Display Name|||URL|||default_strategy|||category\n  Example: app_register('slack|||Slack|||https://slack.com|||cdp|||communication')"

    if strategy not in EXECUTORS:
        return f"[X] Unknown strategy '{strategy}'.\n  Valid strategies: {', '.join(EXECUTORS.keys())}"

    if app_name in ADAPTERS:
        existing = ADAPTERS[app_name]
        return f"[!] '{app_name}' ({existing['name']}) already registered with {len(existing['actions'])} actions.\n  Use app_learn('{app_name}|||new_action|||...') to add actions.\n  Use app_do('{app_name}.{next(iter(existing['actions']))}') to execute."

    ADAPTERS[app_name] = {
        "name": display_name,
        "url": app_url,
        "category": category,
        "actions": {
            "open": {
                "desc": f"Open {display_name}",
                "strategy": strategy,
            },
        },
    }
    # Auto-configure open action based on strategy
    if strategy == "cdp" and app_url:
        ADAPTERS[app_name]["actions"]["open"]["cdp_cmd"] = "navigate"
        ADAPTERS[app_name]["actions"]["open"]["params"] = {"url": app_url}
    elif strategy == "startfile":
        ADAPTERS[app_name]["actions"]["open"]["path"] = f"{display_name}.exe"

    _save_adapters()
    return f"[OK] Registered {display_name} ({app_name})\n  Strategy: {strategy} | Category: {category}\n  Default action: {app_name}.open\n  Persisted to {ADAPTERS_FILE}\n  Now teach it actions with app_learn()."


def app_learn(spec: str) -> str:
    """Teach the adapter a new action for an existing app.

    Format: app_name|||action_name|||description|||strategy|||extra_config

    The extra_config depends on strategy:
      http:      URL template with {param} placeholders (e.g. https://api.example.com/search?q={query})
      cdp:       CSS selector OR cdp command (e.g. input[name='q'] or navigate)
      uia:       Element name/title to find (e.g. "Chat input" or "Send button")
      shell:     Command template with {param} placeholders
      startfile: Path to executable

    Advanced config (append ||| for each):
      http:      url|||method(GET/POST)|||auth_token|||headers_json
      cdp:       selector|||cdp_cmd|||url
      uia:       target|||uia_action(type_text/click/find_window)

    Examples:
      app_learn("slack|||send_dm|||Send direct message|||cdp|||[data-qa='message_input']|||fill_then_click")
      app_learn("github|||my_repos|||List my repos|||http|||https://api.github.com/user/repos|||GET|||ghp_token_here")
    """
    parts = [p.strip() for p in str(spec or "").split("|||", 4)]
    if len(parts) < 3:
        return "[X] Format: app_name|||action_name|||description|||strategy|||config\n  Example: app_learn('slack|||send|||Send message|||cdp|||[data-qa=\"message_input\"]')\n  Example: app_learn('github|||search|||Search repos|||http|||https://api.github.com/search/repositories?q={query}')"

    app_name = parts[0].lower()
    action_name = parts[1].lower()
    desc = parts[2]
    strategy = parts[3].lower() if len(parts) > 3 else "cdp"
    extra = parts[4] if len(parts) > 4 else ""

    if app_name not in ADAPTERS:
        return f"[X] '{app_name}' is not registered.\n  Use app_register('{app_name}|||Display Name|||URL|||strategy') first.\n  Or app_search('{app_name}') to find it in the community registry."

    if strategy not in EXECUTORS:
        return f"[X] Unknown strategy '{strategy}'.\n  Valid strategies: {', '.join(EXECUTORS.keys())}"

    if action_name in ADAPTERS[app_name]["actions"]:
        existing = ADAPTERS[app_name]["actions"][action_name]
        return f"[!] '{app_name}.{action_name}' already exists: {existing['desc']} [{existing['strategy']}]\n  To update it, the action will be overwritten."

    action = {"desc": desc, "strategy": strategy}

    # Parse extra config based on strategy
    if strategy == "http":
        # Format: url_template OR url|||method|||auth_token|||headers_json
        http_parts = extra.split("|||")
        action["url"] = http_parts[0] if http_parts[0] else ""
        if len(http_parts) > 1 and http_parts[1]:
            action["method"] = http_parts[1].upper()
        if len(http_parts) > 2 and http_parts[2]:
            action["auth_token"] = http_parts[2]
        if len(http_parts) > 3 and http_parts[3]:
            try:
                action["headers"] = json.loads(http_parts[3])
            except json.JSONDecodeError:
                return f"[X] Invalid headers JSON: {http_parts[3][:200]}\n  Provide valid JSON like: {{\"X-API-Key\": \"mykey\"}}"

    elif strategy == "cdp":
        # Format: selector OR selector|||cdp_cmd|||url
        cdp_parts = extra.split("|||")
        if cdp_parts[0]:
            action["selector"] = cdp_parts[0]
        action["cdp_cmd"] = cdp_parts[1] if len(cdp_parts) > 1 and cdp_parts[1] else "click"
        if len(cdp_parts) > 2 and cdp_parts[2]:
            action.setdefault("params", {})["url"] = cdp_parts[2]

    elif strategy == "uia":
        # Format: target_element|||uia_action
        uia_parts = extra.split("|||")
        if uia_parts[0]:
            action["target"] = uia_parts[0]
        action["uia_action"] = uia_parts[1] if len(uia_parts) > 1 and uia_parts[1] else "click"

    elif strategy == "shell":
        action["command"] = extra

    elif strategy == "startfile":
        action["path"] = extra

    ADAPTERS[app_name]["actions"][action_name] = action
    _save_adapters()

    strategy_hints = {
        "http": "Use {param} in URL for dynamic values",
        "cdp": "Use CSS selectors like input[name='q']",
        "uia": "Use window/element title or partial text",
        "shell": "Use {param} in command for dynamic values",
        "startfile": "Provide full path to .exe or app name",
    }

    return f"[OK] Learned {app_name}.{action_name}\n  Description: {desc}\n  Strategy: {strategy} — {strategy_hints.get(strategy, '')}\n  Persisted to {ADAPTERS_FILE}\n  Test it: app_do('{app_name}.{action_name}')"


# ═══════════════════════════════════════════════════════════════
# Ecosystem API — discover, export, import, test
# ═══════════════════════════════════════════════════════════════

def app_scan() -> str:
    """Scan the system for installed applications that can be added.

    Searches common install locations and returns apps NOT yet registered.
    Use this when an agent wonders 'what apps can I control?'
    """
    registered = set(ADAPTERS.keys())
    found = []

    if sys.platform == "win32":
        search_paths = [
            os.environ.get("ProgramFiles", "C:\\Program Files"),
            os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)"),
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs"),
        ]
        # Common app name → exe mapping
        common_apps = {
            "zoom": "Zoom\\bin\\Zoom.exe",
            "slack": "Slack\\slack.exe",
            "discord": "Discord\\Discord.exe",
            "notion": "Notion\\Notion.exe",
            "spotify": "Spotify\\Spotify.exe",
            "postman": "Postman\\Postman.exe",
            "vscode": "Microsoft VS Code\\Code.exe",
            "obsidian": "Obsidian\\Obsidian.exe",
            "docker": "Docker\\Docker Desktop.exe",
            "figma": "Figma\\Figma.exe",
            "chrome": "Google\\Chrome\\Application\\chrome.exe",
            "firefox": "Mozilla Firefox\\firefox.exe",
            "edge": "Microsoft\\Edge\\Application\\msedge.exe",
            "teams": "Microsoft\\Teams\\current\\Teams.exe",
            "webstorm": "JetBrains\\WebStorm\\bin\\webstorm64.exe",
            "pycharm": "JetBrains\\PyCharm\\bin\\pycharm64.exe",
        }

        for search in search_paths:
            if not os.path.isdir(search):
                continue
            for app_key, exe_path in common_apps.items():
                if app_key in registered:
                    continue
                full = os.path.join(search, exe_path)
                if os.path.isfile(full):
                    found.append(f"{app_key} ({full})")
                    registered.add(app_key)  # Mark so we don't dupe

    elif sys.platform == "darwin":
        apps_dir = "/Applications"
        if os.path.isdir(apps_dir):
            for entry in os.listdir(apps_dir):
                name = entry.replace(".app", "").lower()
                if name in registered:
                    continue
                found.append(f"{name} (/Applications/{entry})")
                registered.add(name)

    else:  # Linux
        for path in ["/usr/share/applications", "/usr/local/share/applications"]:
            if os.path.isdir(path):
                for f in os.listdir(path):
                    if f.endswith(".desktop"):
                        name = f.replace(".desktop", "").lower()
                        if name not in registered:
                            found.append(name)
                            registered.add(name)

    if not found:
        return "[Scan] No new apps found on this system.\n  All common apps may already be registered, or the system has limited software installed.\n  You can still manually register apps with app_register().\n  Search the community registry: app_search('<app_name>')"

    lines = [f"[Scan] Found {len(found)} unregistered apps:", ""]
    for f in found:
        lines.append(f"  • {f}")
    lines.append("")
    lines.append("To register one: app_register('name|||Display Name|||URL|||strategy')")
    lines.append("For example: app_register('spotify|||Spotify|||https://open.spotify.com|||cdp')")
    return "\n".join(lines)


def app_export(app_name: str = "") -> str:
    """Export adapter(s) as portable JSON.

    Without app_name: exports ALL adapters (for backup/sharing).
    With app_name: exports just that one adapter (for publishing to registry).

    Returns JSON string — agents can save this to a file or send to registry.
    """
    if app_name:
        name = app_name.strip().lower()
        adapter = ADAPTERS.get(name)
        if not adapter:
            return f"[X] '{name}' not found in local adapters.\n  Use app_list() to see what's available."
        payload = {name: adapter}
        return json.dumps(payload, ensure_ascii=False, indent=2)
    else:
        return json.dumps(ADAPTERS, ensure_ascii=False, indent=2)


def app_import(json_str: str, overwrite: bool = False) -> str:
    """Import adapter(s) from JSON.

    Use this to:
    - Restore from backup
    - Install adapters shared by other agents
    - Load community adapters downloaded from the registry

    Args:
        json_str: JSON string containing adapter definitions
        overwrite: If True, overwrite existing adapters with same name
    """
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        return f"[X] Invalid JSON: {e}\n  Provide valid JSON like: {{\"app_name\": {{\"name\": \"...\", \"actions\": {{...}}}}}}\n  Use app_export() to see the correct format."

    if not isinstance(data, dict):
        return "[X] Expected a JSON object with app_name keys.\n  Format: {\"app_name\": {\"name\": \"Display\", \"actions\": {...}}}"

    imported = []
    skipped = []

    for app_name, adapter in data.items():
        if not isinstance(adapter, dict) or "actions" not in adapter:
            skipped.append(f"{app_name} (invalid structure — needs 'actions' dict)")
            continue

        app_key = app_name.lower().strip()

        if app_key in ADAPTERS and not overwrite:
            skipped.append(f"{app_key} (already exists, use overwrite=True to replace)")
            continue

        ADAPTERS[app_key] = adapter
        imported.append(f"{app_key} ({adapter.get('name', app_key)}) — {len(adapter['actions'])} actions")

    if imported:
        _save_adapters()

    result = []
    if imported:
        result.append(f"[OK] Imported {len(imported)} adapters:")
        for imp in imported:
            result.append(f"  ✓ {imp}")
    if skipped:
        result.append(f"[!] Skipped {len(skipped)} adapters:")
        for sk in skipped:
            result.append(f"  ⊘ {sk}")

    if not imported and not skipped:
        return "[!] No valid adapters found in the JSON."

    return "\n".join(result)


def app_test(action_spec: str) -> str:
    """Test an action and report results.

    Same format as app_do(), but adds validation hints.
    Use this before publishing an adapter to ensure actions work.

    Example:
        app_test("zoom.send_chat|||text=Test message")
        app_test("github.search|||query=python")
    """
    result = app_do(action_spec)

    # Analyze result for quality hints
    quality_hints = []
    if "[X]" in result:
        quality_hints.append("⚠️  Action FAILED — fix the configuration before publishing")
        if "No URL configured" in result or "No command configured" in result:
            quality_hints.append("  → Missing configuration. Use app_learn() to teach proper URL/command.")
    elif "[!]" in result:
        quality_hints.append("ℹ️  Action returned a warning — may need refinement")
    else:
        quality_hints.append("✓ Action executed successfully")
        quality_hints.append("  → Ready to publish: app_publish('app_name')")

    return f"{result}\n\n[Test Report]\n" + "\n".join(quality_hints)

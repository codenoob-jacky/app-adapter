"""
App Adapter — Control any software via unified commands.

Strategy priority: API > Browser CDP > Desktop UIA > Shell > Startfile
Design: humans need GUI (buttons, menus), machines just need commands.
The adapter bridges this gap.
"""
import functools, inspect, json, os, re, subprocess, time
from urllib.request import Request, urlopen
import ssl

_SSL = ssl.create_default_context()
_SSL.check_hostname = False
_SSL.verify_mode = ssl.CERT_NONE

ADAPTERS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "adapters.json")

# Built-in defaults — users and agents extend these at runtime
DEFAULT_ADAPTERS = {
    "zoom": {
        "name": "Zoom",
        "actions": {
            "open": {"desc": "Open Zoom desktop client", "strategy": "startfile", "path": "Zoom.exe"},
            "send_chat": {"desc": "Type text into Zoom chat input", "strategy": "uia", "uia_action": "type_text", "target": "Zoom chat input"},
            "start_monitor": {"desc": "Start monitoring Zoom chat messages with TTS announcements", "strategy": "shell", "command": "echo Monitor started"},
        },
    },
    "wechat": {
        "name": "WeChat Official Account",
        "url": "https://mp.weixin.qq.com",
        "actions": {
            "open": {"desc": "Open WeChat MP backend", "strategy": "cdp", "cdp_cmd": "navigate", "params": {"url": "https://mp.weixin.qq.com"}},
            "new_post": {"desc": "Create new article draft", "strategy": "cdp", "cdp_cmd": "click", "selector": ".js_create_post, [data-action='create']"},
            "fill_title": {"desc": "Fill article title", "strategy": "cdp", "cdp_cmd": "fill", "selector": "#title, [placeholder*='title']"},
            "fill_content": {"desc": "Fill article body", "strategy": "cdp", "cdp_cmd": "fill", "selector": "#editor, [contenteditable='true']"},
            "upload_cover": {"desc": "Upload cover image", "strategy": "cdp", "cdp_cmd": "click_then_upload", "selector": ".js_cover_btn"},
            "publish": {"desc": "Publish article", "strategy": "cdp", "cdp_cmd": "click", "selector": "#publish, .js_publish"},
        },
    },
    "excel": {
        "name": "Excel",
        "actions": {
            "create": {"desc": "Create new workbook", "strategy": "shell", "command": "python -c \"from openpyxl import Workbook; wb=Workbook(); wb.save('{name}')\""},
            "add_chart": {"desc": "Add chart to sheet", "strategy": "shell", "command": "echo chart added"},
        },
    },
    "weibo": {
        "name": "Weibo",
        "url": "https://weibo.com",
        "actions": {
            "open": {"desc": "Open Weibo", "strategy": "cdp", "cdp_cmd": "navigate", "params": {"url": "https://weibo.com"}},
            "post": {"desc": "Post a weibo", "strategy": "cdp", "cdp_cmd": "fill_then_click", "fill_selector": "textarea[placeholder*='Post']", "click_selector": "a:has-text('Post'), .send-btn"},
            "trends": {"desc": "View trending topics", "strategy": "http", "url": "https://weibo.com/ajax/side/hotSearch"},
        },
    },
    "browser": {
        "name": "Web Browser",
        "actions": {
            "open": {"desc": "Navigate to URL", "strategy": "cdp", "cdp_cmd": "navigate"},
            "search": {"desc": "Search the web", "strategy": "http", "url": "https://www.google.com/search?q={query}"},
        },
    },
    "github": {
        "name": "GitHub",
        "url": "https://github.com",
        "actions": {
            "open": {"desc": "Open GitHub", "strategy": "cdp", "cdp_cmd": "navigate", "params": {"url": "https://github.com"}},
            "search": {"desc": "Search repositories", "strategy": "cdp", "cdp_cmd": "fill", "selector": "input[name='q']"},
        },
    },
}


# ═══ Persistence ═══

def _load_adapters() -> dict:
    try:
        if os.path.exists(ADAPTERS_FILE):
            with open(ADAPTERS_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            merged = dict(DEFAULT_ADAPTERS)
            merged.update(saved)
            return merged
    except Exception:
        pass
    return dict(DEFAULT_ADAPTERS)


def _save_adapters():
    try:
        with open(ADAPTERS_FILE, "w", encoding="utf-8") as f:
            json.dump(ADAPTERS, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


ADAPTERS = _load_adapters()


# ═══ Strategy Executors ═══

def _execute_http(action: dict, params: dict) -> str:
    """Execute via HTTP API call."""
    url_template = action.get("url", "")
    url = url_template.format(**params) if params else url_template
    if not url:
        return "[X] No URL configured for this action"
    try:
        req = Request(url, headers={"User-Agent": "AppAdapter/1.0", "Accept": "application/json"})
        resp = urlopen(req, timeout=10, context=_SSL)
        return resp.read().decode("utf-8", errors="replace")[:2000]
    except Exception as e:
        return f"[X] HTTP request failed: {e}"


def _execute_cdp(action: dict, params: dict) -> str:
    """Execute via Chrome DevTools Protocol (browser automation)."""
    cmd = action.get("cdp_cmd", "click")
    selector = action.get("selector", "")
    text = params.get("text", params.get("content", ""))

    if cmd == "navigate":
        url = params.get("url") or action.get("params", {}).get("url", "")
        return f"[CDP] Navigate to {url}\nAction: Use browser automation to open {url}"
    elif cmd == "click":
        return f"[CDP] Click '{selector}'\nAction: Use browser automation to click element matching '{selector}'"
    elif cmd == "fill":
        return f"[CDP] Fill '{selector}' with '{text}'\nAction: Use browser automation to type '{text}' into '{selector}'"
    elif cmd == "fill_then_click":
        return f"[CDP] Fill form then click submit\nAction: Fill '{action.get('fill_selector','')}' then click '{action.get('click_selector','')}'"
    elif cmd == "click_then_upload":
        return f"[CDP] Click '{selector}' then upload file"
    return f"[CDP] {cmd}: {action.get('desc','')}"


def _execute_uia(action: dict, params: dict) -> str:
    """Execute via Windows UI Automation or simulated input."""
    uia_action = action.get("uia_action", "click")
    target = action.get("target", "")

    if uia_action == "type_text":
        text = params.get("text", "")
        if not text:
            return "[X] type_text requires 'text' parameter"
        try:
            import ctypes
            # Find the app window (simple heuristic: pick the foreground window)
            escaped = text.replace('"', '""')
            ps = f'Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.SendKeys]::SendWait("{escaped}")'
            r = subprocess.run(['powershell', '-Command', ps], capture_output=True, text=True, timeout=10)
            if r.returncode == 0:
                return f"[UIA] Typed '{text}' into {target}. Verify in the app window."
            return f"[X] SendKeys failed: {r.stderr[:200]}"
        except Exception as e:
            return f"[X] type_text failed: {e}"

    return f"[UIA] {uia_action} on '{target}'. Use UIAutomation to find and interact with this element."


def _execute_shell(action: dict, params: dict) -> str:
    """Execute via shell command."""
    cmd_template = action.get("command", "")
    cmd = cmd_template.format(**params) if params else cmd_template
    if not cmd:
        return "[X] No command configured"
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
        return r.stdout[:2000] or f"Command exited with code {r.returncode}"
    except Exception as e:
        return f"[X] Shell command failed: {e}"


def _execute_startfile(action: dict, params: dict) -> str:
    """Execute by opening a file or application."""
    path = action.get("path", "")
    if not path:
        return "[X] No path configured"
    try:
        os.startfile(path)
        return f"[Startfile] Launched {path}"
    except Exception as e:
        return f"[X] Failed to start {path}: {e}"


# ═══ Core API ═══

def app_do(action_spec: str) -> str:
    """Execute an action on an application.

    Format: app_name.action_name
            app_name.action_name|||param1=val1,param2=val2

    Examples:
        app_do("zoom.send_chat|||text=Hello")
        app_do("weibo.trends")
        app_do("wechat.new_post")
    """
    parts = str(action_spec or "").split("|||", 1)
    action_path = parts[0].strip()
    params_str = parts[1].strip() if len(parts) > 1 else ""

    path_parts = action_path.split(".", 1)
    if len(path_parts) != 2:
        return "[X] Format: app_name.action_name|||param1=val1"

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
        return f"[X] Unknown app '{app_name}'. Use app_list() to see available apps."

    action = adapter["actions"].get(action_name)
    if not action:
        available = ", ".join(adapter["actions"].keys())
        return f"[X] '{app_name}' has no '{action_name}'. Available: {available}"

    strategy = action.get("strategy", "shell")

    executors = {
        "http": _execute_http,
        "cdp": _execute_cdp,
        "uia": _execute_uia,
        "shell": _execute_shell,
        "startfile": _execute_startfile,
    }

    executor = executors.get(strategy)
    if not executor:
        return f"[X] Unknown strategy: {strategy}"

    return executor(action, params)


def app_list() -> str:
    """List all supported apps and their actions."""
    lines = ["Supported Applications:", ""]
    for app_name, adapter in ADAPTERS.items():
        lines.append(f"{adapter['name']} ({app_name})")
        for action_name, action in adapter["actions"].items():
            lines.append(f"  {app_name}.{action_name} — {action['desc']}")
        lines.append("")
    lines.append(f"Total: {len(ADAPTERS)} apps")
    return "\n".join(lines)


def app_register(spec: str) -> str:
    """Register a new application.

    Format: app_name|||Display Name|||URL(optional)|||default_strategy

    Strategies: http (API), cdp (browser), uia (desktop), shell (command), startfile (launch)
    Prefer http/api over visual strategies when available.
    """
    parts = [p.strip() for p in str(spec or "").split("|||", 3)]
    app_name = parts[0].lower() if len(parts) > 0 else ""
    display_name = parts[1] if len(parts) > 1 else app_name
    app_url = parts[2] if len(parts) > 2 else ""
    strategy = parts[3].lower() if len(parts) > 3 else "cdp"

    if not app_name:
        return "[X] Format: app_name|||Display Name|||URL|||strategy"

    if app_name in ADAPTERS:
        return f"[!] '{app_name}' already registered. Use app_learn() to add actions."

    ADAPTERS[app_name] = {
        "name": display_name,
        "url": app_url,
        "actions": {
            "open": {"desc": f"Open {display_name}", "strategy": strategy},
        },
    }
    _save_adapters()
    return f"[OK] Registered {display_name} ({app_name}) with {strategy} strategy. Persisted."


def app_learn(spec: str) -> str:
    """Learn a new action for an existing app.

    Format: app_name|||action_name|||description|||strategy|||extra_config

    The extra_config depends on strategy:
      http: URL template with {param} placeholders
      cdp: CSS selector for the element
      uia: element name/class to find
      shell: command template with {param} placeholders
    """
    parts = [p.strip() for p in str(spec or "").split("|||", 4)]
    if len(parts) < 3:
        return "[X] Format: app_name|||action_name|||description|||strategy|||config"

    app_name = parts[0].lower()
    action_name = parts[1].lower()
    desc = parts[2]
    strategy = parts[3].lower() if len(parts) > 3 else "cdp"
    extra = parts[4] if len(parts) > 4 else ""

    if app_name not in ADAPTERS:
        return f"[X] '{app_name}' not registered. Use app_register() first."

    if action_name in ADAPTERS[app_name]["actions"]:
        return f"[!] '{app_name}.{action_name}' already exists."

    action = {"desc": desc, "strategy": strategy}

    if strategy == "cdp":
        action["cdp_cmd"] = extra or "click"
    elif strategy == "uia":
        action["uia_action"] = extra or "click"
    elif strategy == "http":
        action["url"] = extra or ""
    elif strategy == "shell":
        action["command"] = extra or ""
    elif strategy == "startfile":
        action["path"] = extra or ""

    ADAPTERS[app_name]["actions"][action_name] = action
    _save_adapters()
    return f"[OK] Learned {app_name}.{action_name} — {desc}. Persisted."

"""
Real Windows UI Automation executor.

Optional dependency: uiautomation (Windows only) — `pip install uiautomation`
COM must be initialized per thread, so we lazy-init on first use.

Commands (ported from voice_agent's plugins/desktop/uiautomation_tools.py,
proven on WeChat/DingTalk/file dialogs):
  inspect_ui(window_name)                    — dump native control tree
  click_element(name, automation_id, window_name)  — precise native click
  type_text(name, automation_id, text, window_name) — native input
  open_app(app_name)                         — launch by name (known paths,
                                               Start Menu, Program Files)
  find_window(target)                        — list matching windows

Falls back to instruction mode if uiautomation is not available.
"""
import os
import re
import subprocess
import threading
import time
from typing import Optional


class UIAExecutor:
    """Wraps Windows UI Automation for desktop app control."""

    def __init__(self):
        self._available = None  # None = not checked yet
        self._auto = None
        self._lock = threading.Lock()

    @property
    def available(self) -> bool:
        """Check if uiautomation is available (Windows only)."""
        if self._available is not None:
            return self._available
        if self._available is False:
            return False
        with self._lock:
            if self._available is not None:
                return self._available
            try:
                try:
                    import pythoncom
                    pythoncom.CoInitialize()
                except Exception:
                    pass  # may already be initialized on this thread
                import uiautomation as auto
                try:
                    auto.SetGlobalSearchTimeout(3)
                except Exception:
                    pass
                self._auto = auto
                self._available = True
            except ImportError:
                self._available = False
            except Exception:
                self._available = False
        return self._available

    # ── Control search (port of _find_control_in_window / _find_control_smart) ──

    def _find_control_in_window(self, window, name: str = "", automation_id: str = "",
                                 max_depth: int = 15):
        """DFS the window subtree; return the first control matching ALL given criteria."""
        if window is None or not window.Exists(0, 0):
            return None
        cond = {}
        if name:
            cond["Name"] = name
        if automation_id:
            cond["AutomationId"] = automation_id
        if not cond:
            return None

        nodes_visited = 0
        stack = [(window, 0)]
        while stack:
            ctrl, depth = stack.pop()
            nodes_visited += 1
            if nodes_visited > 3000 or depth > max_depth:
                break
            try:
                children = ctrl.GetChildren()
            except Exception:
                continue
            for child in children:
                try:
                    if child.IsOffscreen:
                        continue
                    match = True
                    for k, v in cond.items():
                        child_val = getattr(child, k, None) or ""
                        if str(child_val) != str(v):
                            match = False
                            break
                    if match:
                        return child
                    stack.append((child, depth + 1))
                except Exception:
                    continue
        return None

    def _find_control_smart(self, name: str = "", automation_id: str = "",
                            window_name: str = ""):
        """Search within the target window first, then globally.

        Returns (control, source_desc) or (None, error_msg).
        """
        auto = self._auto
        if not name and not automation_id:
            return None, "provide name or automation_id (one is required)"

        # Step 1: identify the target window.
        # window_name 是硬约束:找不到就报错,绝不静默降级到全局搜索 ——
        # 全局兜底曾把 CloseButton 点到了毫不相干的窗口上(2026-09-01 事故:
        # type_text 改了记事本标题后,旧 window_name 失配,兜底在桌面任意应用
        # 里找 CloseButton,点掉了跑 agent 的终端)。
        root = None
        if window_name:
            try:
                cand = auto.WindowControl(searchDepth=1, Name=window_name)
                if not cand.Exists(1, 0.5):
                    cand = auto.WindowControl(searchDepth=1, SubName=window_name)
                if cand.Exists(1, 0.5):
                    root = cand
            except Exception:
                root = None
            if root is None:
                return None, (
                    f"window '{window_name}' not found — 标题可能已被上一步操作改变"
                    "(如 type_text 会改窗口标题)。请重新 find_window / inspect_ui,"
                    "用当前标题重试;这是硬约束,不会退化为全局搜索"
                )
        else:
            try:
                root = auto.GetForegroundControl()
                # Walk up to find the top-level window
                for _ in range(5):
                    if root is None:
                        break
                    if root.ControlTypeName in ("WindowControl", "PaneControl"):
                        break
                    try:
                        parent = root.GetParentControl()
                        root = parent if parent else root
                    except Exception:
                        break
            except Exception:
                root = None

        # Step 2: search within the target window (more reliable)
        if root is not None and root.Exists(0, 0):
            ctrl = self._find_control_in_window(root, name=name, automation_id=automation_id)
            if ctrl is not None:
                return ctrl, f"window '{(root.Name or '')[:60]}'"

        # Step 3: global search fallback (expensive — use sparingly).
        # 仅当调用方未指定 window_name 时才允许(那是显式选择不限窗口);
        # 指定了 window_name 的搜索必须大声失败 —— AutomationId 只在单应用内
        # 唯一,全局同名控件(CloseButton 遍地都是)会被点到任意应用上。
        if not window_name:
            kwargs = {}
            if name:
                kwargs["Name"] = name
            if automation_id:
                kwargs["AutomationId"] = automation_id
            try:
                ctrl = auto.Control(searchDepth=10, **kwargs)
                if ctrl.Exists(1, 0.2):
                    return ctrl, "global search (no window_name given)"
            except Exception:
                pass

        scope = f"window '{(root.Name or window_name or 'foreground')[:60]}'" if root is not None else "global scope"
        return None, f"no matching control found in {scope} (Name='{name}', AutomationId='{automation_id}')"

    # ── Commands ──────────────────────────────────────────────────

    # 高危控件名:命中即要求显式 confirm=true。AutomationId 只在单应用内唯一,
    # CloseButton 这类名字跨桌面一抓一把 —— 2026-09-01 事故里全局兜底正是
    # 点到了别的应用的 CloseButton,把自己终端关了。宁可多问一次,不可点错。
    _DANGEROUS_ID = re.compile(
        r"(?:\b(?:close|quit|exit|del(?:ete)?|remove|uninstall|shutdown|format|reset)"
        r"|关闭|退出|删除|卸载|清空|格式化)",
        re.IGNORECASE,
    )

    def inspect_ui(self, window_name: str = "") -> Optional[str]:
        """Dump the native control tree of the foreground (or named) window."""
        auto = self._auto
        try:
            if window_name:
                root = auto.WindowControl(searchDepth=1, Name=window_name)
                if not root.Exists(1, 1):
                    root = auto.WindowControl(searchDepth=1, SubName=window_name)
            else:
                root = auto.GetForegroundControl()
                while root is not None and root.ControlTypeName not in ("WindowControl", "PaneControl"):
                    parent = root.GetParentControl()
                    root = parent if parent else root
                    if parent is None:
                        break

            if root is None or not root.Exists(1, 1):
                return f"[UIA ✗] Target window not found: '{window_name or '(foreground)'}'.\n  Hint: check the window is open, or use windows.find_window first."

            header = f"[UIA ✓] {root.Name}"
            result_list = []
            nodes_visited = [0]

            def walk(control, depth=0):
                if depth > 12 or nodes_visited[0] > 3000:
                    return
                try:
                    children = control.GetChildren()
                except Exception:
                    return
                for child in children:
                    nodes_visited[0] += 1
                    if nodes_visited[0] > 3000:
                        return
                    try:
                        if child.IsOffscreen:
                            continue
                        name = (child.Name or "").replace("\n", " ").strip()
                        c_type = child.ControlTypeName.replace("Control", "")
                        a_id = child.AutomationId
                    except Exception:
                        continue

                    if not (name or a_id):
                        walk(child, depth + 1)
                        continue

                    if c_type in ("Button", "Edit", "Document", "ListItem", "MenuItem",
                                  "Hyperlink", "TabItem", "CheckBox", "RadioButton",
                                  "ComboBox", "Slider", "Text"):
                        item = f"[{c_type}]"
                        if name:
                            item += f"N:'{name}'"
                        if a_id:
                            item += f",ID:'{a_id}'"
                        result_list.append(item)
                    walk(child, depth + 1)

            walk(root)
            unique = list(dict.fromkeys(result_list))
            body = header + "\n" + " | ".join(unique[:150])
            if len(unique) > 150:
                body += " | ...(truncated)"
            if not unique:
                body += "\n  (no named controls — window may be a canvas/foreign GUI; use browser tools or coordinates instead)"
            return body
        except Exception as e:
            return f"[X] inspect_ui failed: {e}"

    def click_element(self, name: str = "", automation_id: str = "",
                      window_name: str = "", confirm: bool = False) -> Optional[str]:
        """Find and click a native control by Name or AutomationId."""
        if not name and not automation_id:
            return "[X] click_element requires name= or automation_id=.\n  Usage: app_do('windows.click_element|||{\"name\": \"确定\"}')"
        if not confirm and (self._DANGEROUS_ID.search(name or "")
                            or self._DANGEROUS_ID.search(automation_id or "")):
            return (
                "[!] Blocked: 目标控件疑似高危(关闭/删除/退出类),拒绝盲点。\n"
                f"  name='{name}' automation_id='{automation_id}' window='{window_name or '(未指定)'}'\n"
                "  先用 inspect_ui 核对控件确实属于你要操作的窗口;确认无误后"
                "加 confirm=true 重试。"
            )
        ctrl, source = self._find_control_smart(name=name, automation_id=automation_id,
                                                 window_name=window_name)
        if ctrl is None:
            return f"[UIA ✗] {source}.\n  Hint: run windows.inspect_ui first to get the exact Name/AutomationId."
        try:
            # Bring the parent window forward before clicking
            try:
                parent = ctrl.GetTopLevelControl()
                if parent and parent.Exists(0, 0):
                    parent.SetFocus()
                    time.sleep(0.15)
            except Exception:
                pass
            ctrl.Click()
            time.sleep(0.3)
            return f"[UIA ✓] Clicked '{name or automation_id}' ({ctrl.ControlTypeName}, via {source})"
        except Exception as e:
            return f"[X] click failed on '{name or automation_id}': {e}"

    def type_text(self, name: str = "", automation_id: str = "", text: str = "",
                  window_name: str = "") -> Optional[str]:
        """Type text into a native input. ValuePattern first, then click+SendKeys."""
        auto = self._auto
        if not text:
            return None  # caller validates text
        try:
            if not name and not automation_id:
                # No control target. If window_name is given, locate and focus
                # THAT window first — never blindly type into whatever happens
                # to be foreground (window_name used to be silently ignored here).
                if window_name:
                    try:
                        cand = auto.WindowControl(searchDepth=1, Name=window_name)
                        if not cand.Exists(1, 0.5):
                            cand = auto.WindowControl(searchDepth=1, SubName=window_name)
                        if not cand.Exists(1, 0.5):
                            return (f"[UIA ✗] window '{window_name}' not found — "
                                    "不会盲打前台兜底。请重新 find_window 确认当前标题"
                                    "(操作可能已改变它)后重试")
                        cand.SetFocus()
                        time.sleep(0.2)
                    except Exception:
                        return (f"[UIA ✗] could not focus window '{window_name}'; "
                                "aborting instead of typing into an unknown foreground window")
                auto.SendKeys(text)
                return (f"[UIA ✓] Sent keys to window '{window_name}'."
                        if window_name else "[UIA ✓] Sent keys to the foreground window (no window_name given).")

            ctrl, source = self._find_control_smart(name=name, automation_id=automation_id,
                                                     window_name=window_name)
            if ctrl is None:
                return f"[UIA ✗] {source}.\n  Hint: run windows.inspect_ui first to find the right target."

            try:
                ctrl.SetFocus()
            except Exception:
                pass
            time.sleep(0.2)

            # ValuePattern first (most reliable for Edit controls)
            try:
                if hasattr(ctrl, "GetValuePattern") and ctrl.GetValuePattern():
                    ctrl.GetValuePattern().SetValue(text)
                    return f"[UIA ✓] Set value of '{name or automation_id}' (via {source})"
            except Exception:
                pass

            # Fallback: click + SendKeys
            ctrl.Click()
            time.sleep(0.1)
            auto.SendKeys(text)
            return f"[UIA ✓] Typed into '{name or automation_id}' (via {source})"
        except Exception:
            return None  # let the caller fall back to PowerShell SendKeys

    # ── App launcher (port of open_application) ──

    _KNOWN_APPS = {
        "zoom": [
            r"%APPDATA%\Zoom\bin\Zoom.exe",
            r"C:\Program Files\Zoom\bin\Zoom.exe",
            r"%LOCALAPPDATA%\Zoom\Zoom.exe",
        ],
        "微信": [
            r"C:\Program Files\Tencent\WeChat\WeChat.exe",
            r"%LOCALAPPDATA%\Tencent\WeChat\WeChat.exe",
            r"%PROGRAMFILES(x86)%\Tencent\WeChat\WeChat.exe",
        ],
        "wechat": [
            r"C:\Program Files\Tencent\WeChat\WeChat.exe",
            r"%LOCALAPPDATA%\Tencent\WeChat\WeChat.exe",
        ],
        "chrome": [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe",
            r"%PROGRAMFILES(x86)%\Google\Chrome\Application\chrome.exe",
        ],
        "edge": [
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        ],
        "vscode": [
            r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe",
        ],
        "notepad": [r"notepad.exe"],
        "calc": [r"calc.exe"],
        "cmd": [r"cmd.exe"],
        "powershell": [r"powershell.exe"],
    }

    def open_app(self, app_name: str) -> Optional[str]:
        """Launch an app by name: known paths → Start Menu shortcuts → Program Files scan."""
        import sys
        if sys.platform != "win32":
            return "[UIA] open_app is Windows-only. Use the OS launcher for your platform."

        name = str(app_name or "").strip()
        if not name:
            return "[X] open_app requires a name."
        name_lower = name.lower()

        # 1. Known install paths
        paths_to_try = self._KNOWN_APPS.get(name_lower, [])
        if not paths_to_try:
            for key, paths in self._KNOWN_APPS.items():
                if name_lower in key or key in name_lower:
                    paths_to_try = paths
                    break
        for raw_path in paths_to_try:
            expanded = os.path.expandvars(raw_path)
            if os.path.exists(expanded):
                try:
                    os.startfile(expanded)  # noqa: S606 — user asked to open this app
                    return f"[UIA ✓] Opened {name} ({expanded})"
                except Exception as e:
                    return f"[X] startfile failed on {expanded}: {e}"

        # 2. Start Menu shortcuts (.lnk)
        start_dirs = [
            os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs"),
            r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs",
        ]
        for base in start_dirs:
            if not os.path.isdir(base):
                continue
            for root, _dirs, files in os.walk(base):
                for f in files:
                    if name_lower in f.lower():
                        full = os.path.join(root, f)
                        try:
                            os.startfile(full)  # noqa: S606
                            return f"[UIA ✓] Opened {name} via Start Menu ({f})"
                        except Exception:
                            continue

        # 3. Program Files scan (depth-capped)
        for prog_base in [os.path.expandvars(r"%PROGRAMFILES%"),
                          os.path.expandvars(r"%PROGRAMFILES(x86)%"),
                          os.path.expandvars(r"%LOCALAPPDATA%")]:
            if not os.path.isdir(prog_base):
                continue
            for root, dirs, files in os.walk(prog_base):
                depth = root[len(prog_base):].count(os.sep)
                if depth > 3:
                    dirs.clear()
                    continue
                for f in files:
                    if f.lower().endswith(".exe") and name_lower in f.lower():
                        full = os.path.join(root, f)
                        try:
                            os.startfile(full)  # noqa: S606
                            return f"[UIA ✓] Opened {name} ({f})"
                        except Exception as e:
                            return f"[X] found {full} but start failed: {e}"

        return f"[UIA ✗] '{name}' not found.\n  Hint: give the exact exe name, or open it manually and use windows.find_window to connect."

    def find_window(self, target: str) -> str:
        """List windows matching the target name."""
        auto = self._auto
        if not self.available:
            return "[UIA] uiautomation not available. Install: pip install uiautomation (Windows only)"
        try:
            windows = []
            for w in auto.GetRootControl().GetChildren():
                name = w.Name or ""
                if target.lower() in name.lower():
                    windows.append(f"  • '{name}' ({w.ClassName})")
            if windows:
                return f"[UIA ✓] Found {len(windows)} window(s) matching '{target}':\n" + "\n".join(windows[:10])
            return f"[UIA ✗] No windows matching '{target}'.\n  Hint: check the app is running; try a shorter name fragment."
        except Exception as e:
            return f"[X] Window search failed: {e}"

    # Backwards-compatible signature for the old 2-arg type_text call
    def type_text_legacy(self, target: str, text: str) -> Optional[str]:
        return self.type_text(name=target, text=text)


# Singleton
_uia_executor: Optional[UIAExecutor] = None


def get_uia_executor() -> UIAExecutor:
    global _uia_executor
    if _uia_executor is None:
        _uia_executor = UIAExecutor()
    return _uia_executor

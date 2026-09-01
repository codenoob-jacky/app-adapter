"""
Regression tests for UIA safety hardening (2026-09-01 incident).

Incident recap: type_text changed a Notepad window's title, the follow-up
click_element(window_name="无标题") missed, the global-search fallback
silently picked a CloseButton from ANOTHER application (the terminal running
the agent itself), and click_element's SetFocus+Click killed it.

These tests pin the three defenses:
  1. window_name is a hard constraint — window miss = error, never global fallback
  2. click_element refuses close/delete/quit-type controls without confirm=true
  3. dangerous-name regex blocks what it should, allows what it should
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app_adapter.uia_executor import UIAExecutor


class _FakeWin:
    """Window stub whose Exists() answer we control."""

    def __init__(self, exists, name="fake"):
        self._exists = exists
        self.Name = name

    def Exists(self, *a, **kw):
        return self._exists


class _FakeAuto:
    """uiautomation stub: records whether global search was ever invoked."""

    def __init__(self, window_exists):
        self._window_exists = window_exists
        self.global_search_calls = 0

    def WindowControl(self, **kw):
        return _FakeWin(self._window_exists)

    def GetForegroundControl(self):
        return _FakeWin(self._window_exists)

    def Control(self, **kw):  # global search path
        self.global_search_calls += 1
        return _FakeWin(False)


def _executor_with(auto):
    ex = UIAExecutor()
    ex._available = True
    ex._auto = auto
    return ex


# ── 1. window_name is a hard constraint ──────────────────────────────

def test_window_name_miss_is_error_not_global_fallback():
    auto = _FakeAuto(window_exists=False)
    ctrl, err = _executor_with(auto)._find_control_smart(name="任意", window_name="ghost")
    assert ctrl is None
    assert "ghost" in err and "not found" in err
    # 硬约束:失配时绝不悄悄全局搜索
    assert auto.global_search_calls == 0


def test_no_window_name_still_allows_global_search():
    auto = _FakeAuto(window_exists=False)
    ctrl, err = _executor_with(auto)._find_control_smart(name="任意")
    assert ctrl is None
    # 未指定 window_name = 调用方显式选择不限窗口,全局兜底仍可用
    assert auto.global_search_calls == 1


def test_click_with_bad_window_reports_window_not_found():
    auto = _FakeAuto(window_exists=False)
    result = _executor_with(auto).click_element(name="无害按钮", window_name="ghost")
    assert "ghost" in result and "not found" in result


# ── 2. dangerous controls require confirm ────────────────────────────

def test_click_close_button_blocked_without_confirm():
    result = UIAExecutor().click_element(automation_id="CloseButton", window_name="某窗口")
    assert result.startswith("[!]")
    assert "confirm" in result


def test_click_close_button_gate_passes_with_confirm():
    # confirm 放行后进入窗口定位;假窗口不存在 → 硬报错(而非被门拦截)
    auto = _FakeAuto(window_exists=False)
    result = _executor_with(auto).click_element(
        automation_id="CloseButton", window_name="ghost", confirm=True)
    assert "not found" in result and not result.startswith("[!]")


def test_app_do_confirm_as_kv_string():
    """k=v 模式的 confirm=true(字符串)也要被认成真。仅在有 UIA 的 Windows 上测。"""
    if sys.platform != "win32" or not UIAExecutor().available:
        return  # 环境不支持,跳过
    from app_adapter import app_do
    r = app_do("windows.click_element|||automation_id=CloseButton,window_name=ghost-xyz,confirm=true")
    assert "ghost-xyz" in r and "not found" in r and "[!]" not in r


# ── 3. dangerous-name regex coverage ─────────────────────────────────

def test_dangerous_regex_blocks():
    rx = UIAExecutor._DANGEROUS_ID
    for s in ["CloseButton", "Close", "关闭标签页", "Button.关闭", "exit",
              "DeleteForever", "确定删除", "uninstall-btn", "关闭程序", "清理并删除"]:
        assert rx.search(s), f"should block: {s}"


def test_dangerous_regex_allows():
    rx = UIAExecutor._DANGEROUS_ID
    for s in ["OK", "发送", "SendButton", "文本编辑器", "AddButton", "搜索框",
              "保存", "disclosed-note", "不保存"]:
        assert not rx.search(s), f"should allow: {s}"

"""
Tests for App Adapter core functionality.

Run: python -m pytest tests/ -v
  or: python tests/test_core.py
"""
import json, os, sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app_adapter import (
    app_do, app_list, app_register, app_learn,
    app_scan, app_export, app_import, app_test,
    app_search, app_install, app_publish,
    ADAPTERS,
)


def test_app_list_returns_string():
    """app_list() should return a non-empty string."""
    result = app_list()
    assert isinstance(result, str)
    assert len(result) > 0
    assert "Total:" in result


def test_app_list_by_category():
    """app_list() with category filter."""
    result = app_list("communication")
    assert isinstance(result, str)
    assert "zoom" in result.lower() or "slack" in result.lower() or "COMMUNICATION" in result.upper()


def test_app_do_invalid_format():
    """app_do() with invalid format should return error."""
    result = app_do("invalid")  # No dot separator
    assert "[X]" in result


def test_app_do_unknown_app():
    """app_do() with unknown app should return error with help."""
    result = app_do("nonexistent.do_something")
    assert "[X]" in result
    assert "Unknown" in result.lower() or "app_search" in result


def test_app_do_unknown_action():
    """app_do() with unknown action should list available actions."""
    result = app_do("zoom.nonexistent_action")
    assert "[X]" in result


def test_app_do_builtin_http():
    """Test HTTP strategy with Weibo trends."""
    result = app_do("weibo.trends")
    assert isinstance(result, str)
    # May succeed or fail depending on network, but shouldn't crash
    assert len(result) > 0


def test_app_do_shell():
    """Test shell strategy."""
    result = app_do("terminal.run|||cmd=echo HelloAppAdapter")
    assert isinstance(result, str)
    assert len(result) > 0


def test_app_register_and_learn_flow():
    """Full flow: register → learn → export → import."""
    test_name = f"test_app_{os.getpid()}"

    # Register
    result = app_register(f"{test_name}|||Test App|||https://example.com|||shell|||utility")
    assert "[OK]" in result or "[!]" in result  # May already exist
    assert test_name in ADAPTERS

    # Learn
    result = app_learn(f"{test_name}|||hello|||Say hello|||shell|||echo Hello {test_name}")
    assert "[OK]" in result or "[!]" in result

    # Verify action exists
    assert "hello" in ADAPTERS[test_name]["actions"]

    # Export
    exported = app_export(test_name)
    assert isinstance(exported, str)
    parsed = json.loads(exported)
    assert test_name in parsed

    # Import (overwrite)
    result = app_import(exported, overwrite=True)
    assert "Imported" in result or "Skipped" in result

    # Cleanup
    del ADAPTERS[test_name]


def test_app_export_all():
    """Export all adapters as JSON."""
    result = app_export()
    assert isinstance(result, str)
    parsed = json.loads(result)
    assert "zoom" in parsed


def test_app_import_invalid_json():
    """Import with invalid JSON should return error."""
    result = app_import("not valid json at all")
    assert "[X]" in result


def test_app_import_valid():
    """Import a valid adapter definition."""
    payload = json.dumps({
        "test_import_app": {
            "name": "Test Import",
            "category": "utility",
            "actions": {
                "open": {"desc": "Open test", "strategy": "shell", "command": "echo test"}
            }
        }
    })
    result = app_import(payload, overwrite=True)
    assert "Imported" in result
    assert "test_import_app" in ADAPTERS
    del ADAPTERS["test_import_app"]


def test_app_test():
    """app_test() should work and include quality hints."""
    result = app_test("terminal.run|||cmd=echo test")
    assert isinstance(result, str)
    assert "Test Report" in result


def test_app_scan():
    """app_scan() should return a string without crashing."""
    result = app_scan()
    assert isinstance(result, str)
    assert len(result) > 0


def test_app_search_empty():
    """app_search() without query should work."""
    result = app_search()
    assert isinstance(result, str)


def test_app_register_invalid_strategy():
    """Register with invalid strategy should error."""
    result = app_register("test_bad|||Test|||url|||invalid_strategy|||util")
    assert "[X]" in result


def test_zero_params():
    """Every app_do should handle empty params gracefully."""
    result = app_do("zoom.send_chat")  # No text param
    assert isinstance(result, str)
    assert len(result) > 0


def test_adapter_persistence():
    """ADAPTERS should have all built-in apps."""
    assert "zoom" in ADAPTERS
    assert "weibo" in ADAPTERS
    assert "github" in ADAPTERS
    assert "terminal" in ADAPTERS
    assert "vscode" in ADAPTERS
    for name, adapter in ADAPTERS.items():
        assert "actions" in adapter
        assert "name" in adapter
        assert len(adapter["actions"]) > 0


if __name__ == "__main__":
    # Simple test runner (no pytest needed)
    tests = [
        ("app_list returns string", test_app_list_returns_string),
        ("app_list by category", test_app_list_by_category),
        ("app_do invalid format", test_app_do_invalid_format),
        ("app_do unknown app", test_app_do_unknown_app),
        ("app_do unknown action", test_app_do_unknown_action),
        ("app_do builtin http", test_app_do_builtin_http),
        ("app_do shell", test_app_do_shell),
        ("register & learn flow", test_app_register_and_learn_flow),
        ("export all", test_app_export_all),
        ("import invalid JSON", test_app_import_invalid_json),
        ("import valid JSON", test_app_import_valid),
        ("app_test with hints", test_app_test),
        ("app_scan", test_app_scan),
        ("app_search empty", test_app_search_empty),
        ("register invalid strategy", test_app_register_invalid_strategy),
        ("app_do zero params", test_zero_params),
        ("adapter structure", test_adapter_persistence),
    ]

    # Fix encoding for Windows terminals
    if sys.platform == "win32":
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    passed = 0
    failed = 0
    for name, test_fn in tests:
        try:
            test_fn()
            print(f"  [PASS] {name}")
            passed += 1
        except Exception as e:
            print(f"  [FAIL] {name}: {e}")
            failed += 1

    print(f"\n{passed} passed, {failed} failed out of {len(tests)} tests")
    if failed:
        sys.exit(1)

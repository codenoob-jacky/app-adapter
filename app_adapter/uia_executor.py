"""
Real Windows UI Automation executor.

Optional dependency: uiautomation (Windows only)
Install: pip install uiautomation

Provides real desktop automation: type text, click buttons, find windows.
Falls back to instruction mode if uiautomation is not available.
"""
import subprocess, sys
from typing import Optional


class UIAExecutor:
    """Wraps Windows UI Automation for desktop app control."""

    def __init__(self):
        self._available = None  # None = not checked yet

    @property
    def available(self) -> bool:
        """Check if uiautomation is available (Windows only)."""
        if self._available is not None:
            return self._available
        if sys.platform != "win32":
            self._available = False
            return False
        try:
            import uiautomation
            self._uia = uiautomation
            self._available = True
        except ImportError:
            self._available = False
        return self._available

    def type_text(self, target: str, text: str) -> Optional[str]:
        """Type text into a target element.

        Tries to find the element by name/class, focus it, then type.
        """
        if not self.available:
            return None

        try:
            # Try to find a focused text input first
            control = self._uia.GetFocusedControl()
            if control and control.ControlTypeName in ("EditControl", "DocumentControl"):
                control.SendKeys(text)
                return f"[UIA ✓] Typed '{text[:100]}' into focused control ({control.Name})"

            # Try to find by target name/automation ID
            if target:
                # Search for matching control
                possible_names = [target, target.lower(), target.replace(" ", "")]
                found = None
                for name in possible_names:
                    try:
                        ctrl = self._uia.ControlFromCursor(0, 0)  # Fallback to root
                        found = self._find_recursive(ctrl, lambda c: name in (c.Name or "").lower())
                        if found:
                            break
                    except Exception:
                        continue

                if found:
                    found.Click()
                    self._uia.WaitForIdle(0.5)
                    found.SendKeys(text)
                    return f"[UIA ✓] Typed '{text[:100]}' into '{found.Name}'"

            # Last resort: just send keys to foreground
            foreground = self._uia.GetForegroundControl()
            if foreground:
                try:
                    foreground.SendKeys(text)
                    return f"[UIA ✓] Sent keys to '{foreground.Name}'"
                except Exception:
                    pass

        except Exception as e:
            pass  # Fall through to PowerShell method

        return None

    def click_element(self, target: str) -> Optional[str]:
        """Find and click an element by name or automation ID."""
        if not self.available:
            return None

        try:
            # Try exact name match
            control = self._find_by_name(target)
            if control:
                control.Click()
                return f"[UIA ✓] Clicked '{control.Name}' ({control.ControlTypeName})"

            # Try partial name match
            control = self._find_by_name(target, exact=False)
            if control:
                control.Click()
                return f"[UIA ✓] Clicked '{control.Name}' ({control.ControlTypeName})"

        except Exception:
            pass

        return None

    def find_window(self, target: str) -> str:
        """Find windows matching the target name."""
        if not self.available:
            return "[UIA] uiautomation not available. Install: pip install uiautomation (Windows only)"

        try:
            windows = []
            for w in self._uia.GetRootControl().GetChildren():
                name = w.Name or ""
                if target.lower() in name.lower():
                    windows.append(f"  • '{name}' ({w.ClassName}) — visible={w.IsOffscreen is False if hasattr(w, 'IsOffscreen') else '?'}")

            if windows:
                return f"[UIA ✓] Found {len(windows)} window(s) matching '{target}':\n" + "\n".join(windows[:10])
            return f"[UIA] No windows matching '{target}' found.\n  Try a different name or check that the app is running."
        except Exception as e:
            return f"[UIA] Window search failed: {e}"

    def _find_by_name(self, name: str, exact: bool = True, max_depth: int = 50):
        """Search the UI tree for a control by name."""
        root = self._uia.GetRootControl()
        return self._find_recursive(root, lambda c: (
            name == (c.Name or "") if exact else name.lower() in (c.Name or "").lower()
        ), max_depth)

    def _find_recursive(self, control, predicate, max_depth: int = 50, depth: int = 0):
        """Recursively search the UI tree."""
        if depth > max_depth:
            return None
        try:
            if predicate(control):
                return control
            for child in control.GetChildren():
                result = self._find_recursive(child, predicate, max_depth, depth + 1)
                if result:
                    return result
        except Exception:
            pass
        return None


# Singleton
_uia_executor: Optional[UIAExecutor] = None


def get_uia_executor() -> UIAExecutor:
    global _uia_executor
    if _uia_executor is None:
        _uia_executor = UIAExecutor()
    return _uia_executor

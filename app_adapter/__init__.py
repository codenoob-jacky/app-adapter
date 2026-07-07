"""App Adapter — Control any software via unified commands."""

from .core import app_do, app_list, app_register, app_learn, ADAPTERS

__version__ = "0.1.0"
__all__ = ["app_do", "app_list", "app_register", "app_learn", "ADAPTERS"]

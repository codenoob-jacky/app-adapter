"""App Adapter — Control any software via unified commands.

Give any AI agent the power to control real software.
Humans need buttons, menus, and forms. Machines just need commands.

Core API:
    app_do("app.action|||param=value")    — Execute an action
    app_list()                             — List all apps & actions
    app_register("app|||Name|||URL|||strategy")  — Register new app
    app_learn("app|||action|||desc|||strategy|||config")  — Teach action

Ecosystem:
    app_scan()                  — Discover installed apps on this system
    app_search("query")         — Search community registry
    app_install("name")         — Install adapter from registry
    app_publish("name")         — Publish adapter to community
    app_export("name")          — Export adapter as JSON
    app_import(json_str)        — Import adapter from JSON
    app_test("app.action|||...")— Test an action with quality report

Usage:
    from app_adapter import app_do, app_list, app_register, app_learn
    from app_adapter import app_scan, app_search, app_install, app_publish
"""

from .core import app_do, app_list, app_register, app_learn, ADAPTERS
from .core import app_scan, app_export, app_import, app_test
from .registry import app_search, app_install, app_publish
from .prompts import (
    get_agent_prompt, get_welcome_message, get_contribution_nudge,
    get_strategy_tip, AGENT_SYSTEM_PROMPT, WELCOME_PROMPT,
)

__version__ = "0.3.0"
__all__ = [
    # Core
    "app_do", "app_list", "app_register", "app_learn", "ADAPTERS",
    # Ecosystem
    "app_scan", "app_export", "app_import", "app_test",
    # Registry
    "app_search", "app_install", "app_publish",
    # Prompts
    "get_agent_prompt", "get_welcome_message",
    "AGENT_SYSTEM_PROMPT", "WELCOME_PROMPT",
]

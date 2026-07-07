"""
Entry point for `python -m app_adapter` and `app-adapter` CLI.

Usage:
    python -m app_adapter                  # Quick demo (list + scan)
    python -m app_adapter server --port 8080  # Start HTTP server
    python -m app_adapter server --mcp        # Start MCP stdio server
    python -m app_adapter do "zoom.send_chat|||text=Hi"  # Execute one action
    python -m app_adapter list                 # List all apps
    python -m app_adapter scan                 # Scan for installable apps
    python -m app_adapter search "spotify"      # Search registry
    python -m app_adapter prompt               # Print system prompt for agents
"""
import argparse, json, sys


def cmd_server(args):
    """Start MCP/HTTP server."""
    import os
    server_py = os.path.join(os.path.dirname(__file__), "..", "server.py")
    argv = [server_py]
    if args.mcp or args.http:
        argv.append("--http" if args.http else "--port")
        if args.port:
            argv.extend([str(args.port)])
    # Use subprocess to avoid import issues with MCP
    import subprocess
    subprocess.run([sys.executable] + argv)


def cmd_do(args):
    """Execute a single action."""
    from app_adapter import app_do
    print(app_do(args.action))


def cmd_list(args):
    """List all apps."""
    from app_adapter import app_list
    print(app_list(args.category or ""))


def cmd_scan(args):
    """Scan for installable apps."""
    from app_adapter import app_scan
    print(app_scan())


def cmd_search(args):
    """Search the community registry."""
    from app_adapter import app_search
    print(app_search(args.query or ""))


def cmd_prompt(args):
    """Print the agent system prompt (for injecting into Claude/Codex/etc.)."""
    from app_adapter import get_agent_prompt, get_welcome_message
    style = args.style or "full"
    if style == "welcome":
        print(get_welcome_message())
    else:
        print(get_agent_prompt(style))


def cmd_export(args):
    """Export adapter as JSON."""
    from app_adapter import app_export
    print(app_export(args.app or ""))


def cmd_register(args):
    """Register a new app."""
    from app_adapter import app_register
    print(app_register(args.spec))


def cmd_learn(args):
    """Teach a new action."""
    from app_adapter import app_learn
    print(app_learn(args.spec))


def cmd_test(args):
    """Test an action."""
    from app_adapter import app_test
    print(app_test(args.action))


def main():
    parser = argparse.ArgumentParser(
        prog="app-adapter",
        description="App Adapter — Control any software via unified commands. The AI-to-App bridge.",
    )
    sub = parser.add_subparsers(dest="command", help="Commands")

    # server
    p = sub.add_parser("server", help="Start MCP/HTTP server")
    p.add_argument("--port", type=int, default=8080, help="HTTP port (default: 8080)")
    p.add_argument("--mcp", action="store_true", help="Force MCP stdio mode")
    p.add_argument("--http", action="store_true", help="Force HTTP mode")

    # do
    p = sub.add_parser("do", help="Execute an action")
    p.add_argument("action", help="Action spec: app.action|||param=value")

    # list
    p = sub.add_parser("list", help="List all apps and actions")
    p.add_argument("category", nargs="?", help="Filter by category")

    # scan
    sub.add_parser("scan", help="Scan system for installable apps")

    # search
    p = sub.add_parser("search", help="Search community registry")
    p.add_argument("query", nargs="?", help="Search query")

    # prompt
    p = sub.add_parser("prompt", help="Print system prompt for agents")
    p.add_argument("--style", choices=["full", "brief", "nudge", "welcome"], default="full")

    # export
    p = sub.add_parser("export", help="Export adapter as JSON")
    p.add_argument("app", nargs="?", help="App name (empty = all)")

    # register
    p = sub.add_parser("register", help="Register a new app")
    p.add_argument("spec", help="Registration spec: name|||Display|||URL|||strategy|||category")

    # learn
    p = sub.add_parser("learn", help="Teach a new action")
    p.add_argument("spec", help="Learning spec: app|||action|||desc|||strategy|||config")

    # test
    p = sub.add_parser("test", help="Test an action")
    p.add_argument("action", help="Action to test: app.action|||param=value")

    args = parser.parse_args()

    handlers = {
        "server": cmd_server,
        "do": cmd_do,
        "list": cmd_list,
        "scan": cmd_scan,
        "search": cmd_search,
        "prompt": cmd_prompt,
        "export": cmd_export,
        "register": cmd_register,
        "learn": cmd_learn,
        "test": cmd_test,
    }

    if args.command in handlers:
        handlers[args.command](args)
    else:
        # No command: quick demo
        print("=" * 60)
        print("  App Adapter v0.3.0 — The AI-to-App Bridge")
        print("=" * 60)
        from app_adapter import app_list, app_scan
        print("\nQuick overview:")
        cats = ["communication", "social", "development", "productivity"]
        for cat in cats:
            result = app_list(cat)
            # Print just the summary line
            lines = result.split("\n")
            for line in lines:
                if "Total:" in line:
                    print(f"  {cat}: {line.strip()}")
                    break
        print(f"\n  app_scan() → {app_scan().split(chr(10))[0]}")
        print(f"\n  Try: app-adapter server --port 8080")
        print(f"  Try: app-adapter prompt --style full")
        print(f"  Try: app-adapter prompt --style brief  # inject this into your agent")


if __name__ == "__main__":
    main()

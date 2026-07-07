"""
App Adapter MCP Server — Expose app_do/register/learn/search to any MCP-compatible agent.

Usage:
  python server.py                          # MCP stdio (Claude Desktop, Codex, etc.)
  python server.py --port 8080              # HTTP mode (any agent via REST)
  python server.py --http                   # Force HTTP mode even if MCP is installed

HTTP API (POST /):
  {"tool": "app_list"}
  {"tool": "app_scan"}
  {"tool": "app_search", "arguments": {"query": "slack"}}
  {"tool": "app_do", "arguments": {"action": "zoom.send_chat|||text=Hello"}}
  {"tool": "app_register", "arguments": {"spec": "slack|||Slack|||https://slack.com|||cdp|||communication"}}
  {"tool": "app_learn", "arguments": {"spec": "slack|||send|||Send message|||cdp|||[data-qa=\"input\"]|||fill_then_click"}}
  {"tool": "app_install", "arguments": {"name": "slack"}}
  {"tool": "app_publish", "arguments": {"app_name": "my_slack"}}
  {"tool": "app_export", "arguments": {"app_name": ""}}
  {"tool": "app_import", "arguments": {"json_str": "{...}"}}
  {"tool": "app_test", "arguments": {"action": "zoom.send_chat|||text=Test"}}

Claude Desktop Config (claude_desktop_config.json):
{
  "mcpServers": {
    "app-adapter": {
      "command": "python",
      "args": ["server.py"],
      "cwd": "/path/to/app-adapter"
    }
  }
}
"""
import sys, os, json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
HTTP_MODE = "--port" in sys.argv or "--http" in sys.argv


def get_tools():
    """Lazy import to avoid slow startup."""
    from app_adapter import (
        app_do, app_list, app_register, app_learn,
        app_scan, app_export, app_import, app_test,
        app_search, app_install, app_publish,
    )
    return {
        "app_do": app_do,
        "app_list": app_list,
        "app_register": app_register,
        "app_learn": app_learn,
        "app_scan": app_scan,
        "app_export": app_export,
        "app_import": app_import,
        "app_test": app_test,
        "app_search": app_search,
        "app_install": app_install,
        "app_publish": app_publish,
    }


def handle(name: str, args: dict) -> str:
    tools = get_tools()
    func = tools.get(name)
    if not func:
        return json.dumps({"error": f"Unknown tool: {name}", "available": list(tools.keys())})

    try:
        if name == "app_do":
            return func(str(args.get("action", args.get("spec", ""))))
        elif name == "app_list":
            return func(args.get("category", ""))
        elif name == "app_register":
            return func(str(args.get("spec", "")))
        elif name == "app_learn":
            return func(str(args.get("spec", "")))
        elif name == "app_search":
            return func(str(args.get("query", "")))
        elif name == "app_install":
            return func(str(args.get("name", "")))
        elif name == "app_publish":
            return func(str(args.get("app_name", "")), str(args.get("message", "")))
        elif name == "app_export":
            return func(str(args.get("app_name", "")))
        elif name == "app_import":
            return func(str(args.get("json_str", "")), bool(args.get("overwrite", False)))
        elif name == "app_test":
            return func(str(args.get("action", "")))
        elif name == "app_scan":
            return func()
        return func()
    except Exception as e:
        return json.dumps({"error": str(e)})


# ═══ MCP stdio mode ═══

try:
    from mcp.server import Server, NotificationOptions
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent
    HAS_MCP = True
except ImportError:
    HAS_MCP = False

if HAS_MCP and not HTTP_MODE:
    app = Server("app-adapter")

    @app.list_tools()
    async def list_tools():
        return [
            # Core
            Tool(name="app_do", description="Execute app action. Format: app.action|||param=value. E.g. zoom.send_chat|||text=Hello",
                 inputSchema={"type": "object", "properties": {"action": {"type": "string", "description": "Action spec: app.action|||param1=val1,param2=val2"}}, "required": ["action"]}),
            Tool(name="app_list", description="List all supported apps and their actions. Optional category filter.",
                 inputSchema={"type": "object", "properties": {"category": {"type": "string", "description": "Filter by category: communication, social, productivity, development, design, finance, utility"}}}),
            Tool(name="app_register", description="Register new app: app_name|||Display Name|||URL|||strategy(http/cdp/uia/shell/startfile)|||category",
                 inputSchema={"type": "object", "properties": {"spec": {"type": "string", "description": "Registration spec"}}, "required": ["spec"]}),
            Tool(name="app_learn", description="Teach new action: app|||action|||desc|||strategy|||config. Config depends on strategy: URL for http, selector for cdp, element name for uia, command for shell.",
                 inputSchema={"type": "object", "properties": {"spec": {"type": "string", "description": "Learning spec"}}, "required": ["spec"]}),
            # Ecosystem
            Tool(name="app_scan", description="Scan system for installed applications that can be registered.",
                 inputSchema={"type": "object", "properties": {}}),
            Tool(name="app_export", description="Export adapter(s) as JSON. Leave app_name empty to export all.",
                 inputSchema={"type": "object", "properties": {"app_name": {"type": "string", "description": "App name to export (empty = all)"}}}),
            Tool(name="app_import", description="Import adapter(s) from JSON string.",
                 inputSchema={"type": "object", "properties": {"json_str": {"type": "string", "description": "JSON adapter definition"}, "overwrite": {"type": "boolean", "description": "Overwrite existing adapters"}}, "required": ["json_str"]}),
            Tool(name="app_test", description="Test an action and get a quality report. Same format as app_do.",
                 inputSchema={"type": "object", "properties": {"action": {"type": "string", "description": "Action to test: app.action|||param=value"}}, "required": ["action"]}),
            # Registry
            Tool(name="app_search", description="Search community registry for adapters. Leave query empty to list all.",
                 inputSchema={"type": "object", "properties": {"query": {"type": "string", "description": "Search query (app name or keyword)"}}}),
            Tool(name="app_install", description="Install adapter from community registry by name.",
                 inputSchema={"type": "object", "properties": {"name": {"type": "string", "description": "Adapter name to install"}}, "required": ["name"]}),
            Tool(name="app_publish", description="Prepare adapter for publishing to community registry. Includes validation and quality checks.",
                 inputSchema={"type": "object", "properties": {"app_name": {"type": "string", "description": "App name to publish"}, "message": {"type": "string", "description": "Optional commit message"}}, "required": ["app_name"]}),
        ]

    @app.call_tool()
    async def call_tool(name: str, arguments: dict):
        return [TextContent(type="text", text=handle(name, arguments))]

    async def run():
        async with stdio_server() as (read, write):
            await app.run(read, write, app.create_initialization_options())

    def main():
        import asyncio
        asyncio.run(run())

else:
    # ═══ HTTP fallback ═══
    from http.server import HTTPServer, BaseHTTPRequestHandler

    class Handler(BaseHTTPRequestHandler):
        def _send(self, data, code=200):
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)

        def do_OPTIONS(self):
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()

        def do_POST(self):
            try:
                length = int(self.headers.get("Content-Length", 0))
                raw = self.rfile.read(length) if length > 0 else b"{}"
                body = json.loads(raw.decode("utf-8"))
            except Exception:
                return self._send({"error": "Invalid JSON"}, 400)

            tool = body.get("tool", body.get("name", ""))
            args = body.get("arguments", body.get("params", body))
            self._send({"result": str(handle(tool, args))})

        def do_GET(self):
            tool_help = {
                "tools": sorted(get_tools().keys()),
                "usage": {
                    "POST /": "Execute a tool. Body: {\"tool\": \"name\", \"arguments\": {...}}",
                    "GET /": "This help page",
                },
                "examples": {
                    "list_apps": 'curl -X POST http://localhost:8080 -H "Content-Type: application/json" -d \'{"tool":"app_list"}\'',
                    "scan_system": 'curl -X POST http://localhost:8080 -H "Content-Type: application/json" -d \'{"tool":"app_scan"}\'',
                    "search_registry": 'curl -X POST http://localhost:8080 -H "Content-Type: application/json" -d \'{"tool":"app_search","arguments":{"query":"slack"}}\'',
                    "execute_action": 'curl -X POST http://localhost:8080 -H "Content-Type: application/json" -d \'{"tool":"app_do","arguments":{"action":"zoom.send_chat|||text=Hello"}}\'',
                },
            }
            self._send(tool_help)

        def log_message(self, *args):
            pass  # Suppress access logs

    def main():
        port = None
        for i, arg in enumerate(sys.argv):
            if arg == "--port" and i + 1 < len(sys.argv):
                port = int(sys.argv[i + 1])
                break
        if port is None:
            port = 8080

        print(f"App Adapter MCP Server v0.2.0 — {len(get_tools())} tools")
        print(f"HTTP mode: http://localhost:{port}")
        print(f"Try: curl -X POST http://localhost:{port} -H 'Content-Type: application/json' -d '{{\"tool\":\"app_list\"}}'")
        HTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    main()

"""
App Adapter MCP Server — Expose app_do/register/learn to any MCP-compatible agent.

Usage:
  python server.py                    # MCP stdio (Claude Desktop, Codex, etc.)
  python server.py --port 8080        # HTTP mode (any agent via REST)

HTTP API (POST /):
  {"tool": "app_list"}
  {"tool": "app_do", "arguments": {"action": "zoom.send_chat|||text=Hello"}}
  {"tool": "app_register", "arguments": {"spec": "slack|||Slack|||https://slack.com|||cdp"}}
  {"tool": "app_learn", "arguments": {"spec": "slack|||send|||Send message|||cdp|||fill_then_click"}}

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
HTTP_MODE = "--port" in sys.argv


def get_tools():
    from app_adapter import app_do, app_list, app_register, app_learn
    return app_do, app_list, app_register, app_learn


def handle(name: str, args: dict) -> str:
    do, lst, reg, learn = get_tools()
    try:
        if name == "app_list":
            return lst()
        elif name == "app_do":
            return do(str(args.get("action", args.get("spec", ""))))
        elif name == "app_register":
            return reg(str(args.get("spec", "")))
        elif name == "app_learn":
            return learn(str(args.get("spec", "")))
        return json.dumps({"error": f"Unknown tool: {name}"})
    except Exception as e:
        return json.dumps({"error": str(e)})


# MCP stdio mode
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
            Tool(name="app_do", description="Execute app action. Format: app.action|||k=v. E.g. zoom.send_chat|||text=Hello",
                 inputSchema={"type": "object", "properties": {"action": {"type": "string"}}, "required": ["action"]}),
            Tool(name="app_list", description="List all supported apps and their actions",
                 inputSchema={"type": "object", "properties": {}}),
            Tool(name="app_register", description="Register new app: name|||Display|||URL|||strategy(http/cdp/uia/shell/startfile)",
                 inputSchema={"type": "object", "properties": {"spec": {"type": "string"}}, "required": ["spec"]}),
            Tool(name="app_learn", description="Learn new action: app|||action|||desc|||strategy|||config",
                 inputSchema={"type": "object", "properties": {"spec": {"type": "string"}}, "required": ["spec"]}),
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
    # HTTP fallback
    from http.server import HTTPServer, BaseHTTPRequestHandler

    class Handler(BaseHTTPRequestHandler):
        def _send(self, data, code=200):
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

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
            self._send({"tools": ["app_do", "app_list", "app_register", "app_learn"]})

        def log_message(self, *args):
            pass

    def main():
        port = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[1] == "--port" else 8080
        print(f"App Adapter MCP Server on http://localhost:{port}")
        HTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    main()

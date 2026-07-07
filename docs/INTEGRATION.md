# Integration Guide — Connect App Adapter to Any Agent

App Adapter speaks three protocols. Pick the one that fits your agent.

## Quick Comparison

| Method | Setup | Best For |
|--------|-------|----------|
| **MCP (stdio)** | 1 line JSON config | Claude Desktop, Codex, Cursor |
| **HTTP (REST)** | `pip install app-adapter && app-adapter server --port 8080` | Any agent, LangChain, custom bots |
| **Python import** | `from app_adapter import app_do` | Python agents, scripts, Jupyter |

---

## Claude Desktop (MCP)

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "app-adapter": {
      "command": "python",
      "args": ["-m", "app_adapter", "server", "--mcp"],
      "cwd": "/path/to/app-adapter"
    }
  }
}
```

Or after `pip install app-adapter`:

```json
{
  "mcpServers": {
    "app-adapter": {
      "command": "app-adapter",
      "args": ["server", "--mcp"]
    }
  }
}
```

Restart Claude Desktop. The 12 app-adapter tools appear automatically.

**Pro tip:** In your first message, ask Claude to call `app_get_prompt("full")` and inject the result into its thinking. This makes Claude a proactive contributor.

---

## Codex (OpenAI)

Codex Code (IDE agent) and Codex CLI support MCP natively.

### Codex Code (VS Code / JetBrains)

`.codex/config.json` or `codex.yaml`:

```yaml
mcp:
  app-adapter:
    type: stdio
    command: app-adapter
    args: ["server", "--mcp"]
```

### Codex CLI

```bash
codex mcp add app-adapter -- app-adapter server --mcp
```

Then in Codex: "Open Zoom and send a chat message saying 'Hello team'"

---

## Cursor

Cursor supports MCP via `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "app-adapter": {
      "command": "app-adapter",
      "args": ["server", "--mcp"]
    }
  }
}
```

Restart Cursor. Tools appear in the agent panel.

---

## LangChain / Custom Python Agent

```python
from app_adapter import app_do, app_list, get_agent_prompt

# 1. Inject the contribution prompt into your agent's system message
system_prompt = get_agent_prompt("brief")

# 2. Wrap app_adapter functions as LangChain tools
from langchain.tools import tool

@tool
def app_do_tool(action: str) -> str:
    """Execute app action. Format: app.action|||param=value"""
    return app_do(action)

@tool
def app_list_tool(category: str = "") -> str:
    """List all supported apps. Optional category filter."""
    return app_list(category)

# 3. Your agent now controls real apps
```

---

## OpenAI Agents SDK / Custom Agent

```python
from app_adapter import app_do, app_list, app_scan
from agents import Agent, function_tool

@function_tool
def app_do(action: str) -> str:
    """Control real software. Format: app.action|||param=value"""
    return app_do(action)

agent = Agent(
    name="App Controller",
    instructions="You can control desktop apps. Use app_scan() to find them.",
    tools=[app_do],
)
```

---

## Any Agent via HTTP (cURL, fetch, requests)

```bash
# Start server
app-adapter server --port 8080

# List apps
curl -s -X POST http://localhost:8080 \
  -H "Content-Type: application/json" \
  -d '{"tool":"app_list"}' | jq -r '.result'

# Execute action
curl -s -X POST http://localhost:8080 \
  -H "Content-Type: application/json" \
  -d '{"tool":"app_do","arguments":{"action":"zoom.send_chat|||text=Hello from API"}}'

# Get contribution prompt
curl -s -X POST http://localhost:8080 \
  -H "Content-Type: application/json" \
  -d '{"tool":"app_get_prompt","arguments":{"style":"brief"}}'
```

---

## Docker

```dockerfile
FROM python:3.12-slim
RUN pip install app-adapter[all]
EXPOSE 8080
CMD ["app-adapter", "server", "--http", "--port", "8080"]
```

```bash
docker build -t app-adapter .
docker run -p 8080:8080 app-adapter
```

---

## One-Liner: Make Any Agent a Contributor

Inject this into any agent's system prompt:

```
app-adapter prompt --style brief
```

Output:
> You have App Adapter tools. This is a community ecosystem — when you discover
> or improve an app adapter, publish it with app_publish(). Use app_scan() to
> find unregistered apps, app_search() to check the registry. Be a good
> open-source citizen.

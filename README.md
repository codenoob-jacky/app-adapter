# App Adapter — Control Any Software via Commands

**The AI-to-App Bridge.** Give any AI agent the power to control real software.

Humans need buttons, menus, and forms. Machines just need commands.  
`app_do("zoom.send_chat|||text=Hello")` — that's it.

## Why

Current AI agents are trapped in the browser. They can read web pages but can't *do* things in real apps.
Codex's Record & Replay watches your screen and replays clicks. That's visual — slow, fragile, and expensive.

**App Adapter translates human GUI actions into machine-executable commands.**
No screen recording. No pixel matching. Just `app.do("action", {params})`.

## How It Works

```
┌──────────┐     ┌──────────────┐     ┌──────────┐
│ Any Agent │ ──▶ │ App Adapter  │ ──▶ │ Real App │
│ (Claude,  │     │ (MCP Server) │     │ (Zoom,   │
│  Codex,   │     │              │     │  WeChat, │
│  Cursor)  │     │ Strategies:  │     │  Excel,  │
│           │     │ • http/api   │     │  etc.)   │
│           │     │ • cdp/browser│     │          │
│           │     │ • uia/desktop│     │          │
│           │     │ • shell/cmd  │     │          │
└──────────┘     └──────────────┘     └──────────┘
```

### Strategy Priority

| Strategy | Use When | Speed | Reliability |
|----------|----------|-------|-------------|
| `http` | App has a REST API | Fast | High |
| `cdp` | App has a web interface | Medium | Medium |
| `uia` | Desktop-only app, no API | Slow | Low |
| `shell` | CLI tool or script | Fast | High |
| `startfile` | Just need to open the app | Instant | High |

**Prefer `http` over visual strategies. Always.** Visual automation is the last resort for apps without APIs.

## Quick Start

```bash
# 1. Install
git clone https://github.com/codenoob-jacky/app-adapter.git
cd app-adapter
pip install -r requirements.txt

# 2. Start the MCP server
python server.py --port 8080

# 3. Any agent can now control your apps
curl -X POST http://localhost:8080 \
  -H "Content-Type: application/json" \
  -d '{"tool":"app_list"}'

curl -X POST http://localhost:8080 \
  -H "Content-Type: application/json" \
  -d '{"tool":"app_do","arguments":{"action":"zoom.send_chat|||text=Hello from AI"}}'
```

## Connect to Your Agent

### Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "app-adapter": {
      "command": "python",
      "args": ["server.py"],
      "cwd": "/path/to/app-adapter"
    }
  }
}
```

### Any MCP-Compatible Agent

The server speaks the [Model Context Protocol](https://modelcontextprotocol.io) natively.
Run `python server.py` for stdio mode — works with Codex, Cursor, and any MCP client.

### Any Agent via HTTP

```bash
python server.py --port 8080
# POST / with {"tool": "app_do", "arguments": {"action": "..."}}
```

## Built-in Apps

| App | Actions |
|-----|---------|
| **Zoom** | open, send_chat, start_monitor |
| **WeChat MP** | open, new_post, fill_title, fill_content, upload_cover, publish |
| **Weibo** | open, post, trends |
| **Excel** | create, add_chart |
| **GitHub** | open, search |
| **Browser** | open, search |

## Self-Evolution

The adapter learns. Agents can register new apps and teach new actions at runtime:

```python
# Register a new app
app_register("slack|||Slack|||https://slack.com|||cdp")

# Teach it actions  
app_learn("slack|||send_message|||Send a Slack message|||cdp|||fill_then_click")

# Now use it
app_do("slack.send_message|||text=Hello team")
```

All learned apps persist to `adapters.json` — survive restarts, shareable across agents.

## Design Philosophy

> Humans use GUI. Machines need commands.
> The adapter is the translation layer.
> Don't make AI learn to see — teach apps to listen.

## License

MIT

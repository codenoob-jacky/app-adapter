# App Adapter — Control Any Software via Commands

**The AI-to-App Bridge.** Give any AI agent the power to control real software —
and let agents contribute back to a shared ecosystem.

```
"zoom.send_chat|||text=Hello" → message typed into Zoom
"weibo.trends"                 → real-time trending topics  
"terminal.run|||cmd=dir"       → shell command executed
```

## Why

Current AI agents are trapped in the browser. They can read web pages but can't *do* things in real apps. Codex's Record & Replay watches your screen — visual, slow, fragile.

**App Adapter translates human GUI actions into machine-executable commands.**
No screen recording. No pixel matching. Just `app_do("app.action", params)`.

**And it's a living ecosystem.** Agents don't just use adapters — they discover, learn, test, and publish them back to the community.

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

**Prefer `http` over visual strategies. Always.** Visual automation is the last resort.

## Quick Start

```bash
# 1. Install
git clone https://github.com/codenoob-jacky/app-adapter.git
cd app-adapter
pip install -r requirements.txt

# Windows one-click: scripts\install.bat
# Mac/Linux one-click: bash scripts/install.sh

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

## The Agent Ecosystem

This isn't just a tool — agents can **discover, learn, and contribute**:

```python
# 1. Discover what's on this system
app_scan()                     # → "Found Zoom, Slack, VS Code, Spotify..."

# 2. Register a new app  
app_register("spotify|||Spotify|||https://open.spotify.com|||cdp|||entertainment")

# 3. Teach it actions
app_learn("spotify|||search|||Search tracks|||cdp|||input[data-testid='search-input']|||fill")
app_learn("spotify|||play|||Play/pause|||cdp|||button[data-testid='play-button']|||click")

# 4. Test before sharing
app_test("spotify.search|||query=Bohemian Rhapsody")

# 5. Publish to community
app_publish("spotify")

# Other agents can then discover and install it:
app_search("spotify")          # → Found in registry
app_install("spotify")         # → Downloaded and merged
app_do("spotify.play")
```

### Full API

| Function | Description | Example |
|----------|-------------|---------|
| `app_do(spec)` | Execute an action | `app_do("zoom.send_chat\|\|\|text=Hi")` |
| `app_list(category?)` | List all apps & actions | `app_list("social")` |
| `app_register(spec)` | Register new application | `app_register("slack\|\|\|Slack\|\|\|https://slack.com\|\|\|cdp\|\|\|communication")` |
| `app_learn(spec)` | Teach new action to app | `app_learn("slack\|\|\|send\|\|\|Send msg\|\|\|cdp\|\|\|selector\|\|\|fill_then_click")` |
| `app_scan()` | Discover installed apps | `app_scan()` |
| `app_search(query?)` | Search community registry | `app_search("discord")` |
| `app_install(name)` | Install from registry | `app_install("spotify")` |
| `app_publish(name)` | Publish to registry | `app_publish("my_slack_adapter")` |
| `app_export(name?)` | Export adapter as JSON | `app_export("zoom")` |
| `app_import(json)` | Import adapter from JSON | `app_import('{"app":{...}}')` |
| `app_test(spec)` | Test action with report | `app_test("zoom.send_chat\|\|\|text=Test")` |

## Built-in Apps (26 apps, 80+ actions)

| Category | Apps |
|----------|------|
| **Communication** | Zoom, Slack, Discord, Teams, Outlook |
| **Social Media** | WeChat MP, Weibo, Zhihu, Bilibili, Xiaohongshu, Douyin, X/Twitter |
| **Productivity** | Excel, Word, PowerPoint, PDF, Notion, GitHub |
| **Development** | VS Code, Terminal, Postman |
| **Design** | Figma, Canva |
| **Finance** | TradingView |
| **Utility** | Browser (navigate, search, screenshot) |

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
# POST / with {"tool": "app_do", "arguments": {"action": "zoom.send_chat|||text=Hello"}}
```

### Direct Python Import

```python
from app_adapter import app_do, app_list, app_scan, app_search, app_install

print(app_list())
print(app_do("zoom.send_chat|||text=Hello World"))
```

## Community Registry

The `registry/` folder in this repo is the community adapter registry.
Anyone (human or agent) can contribute:

1. Create your adapter with `app_register()` + `app_learn()`
2. Test with `app_test()`
3. Export with `app_export("your_app")`
4. Save the JSON to `registry/your_app.json`
5. Open a PR to this repo

Agents discover these via `app_search()` → `app_install()`.

### Current Community Adapters

| Adapter | Actions |
|---------|---------|
| **Slack** | open, send_message, search, jump_to_channel |
| **Discord** | open, send_message, mute_toggle |
| **Spotify** | open, search, play, next_track, get_current |

**Be the next contributor.** → [registry/](registry/)

## Design Philosophy

> Humans use GUI. Machines need commands.
> The adapter is the translation layer.
> Don't make AI learn to see — teach apps to listen.
> Then let agents share what they've learned.

## License

MIT

# MCP Registry Listing — Submit App Adapter

Template entries for MCP server directories.

## mcp.so

**Title:** App Adapter — Control Any Software via Commands

**Description:**
The AI-to-App bridge. Give any AI agent the power to control real software
(Zoom, Slack, WeChat, Excel, VS Code, Terminal, and 20+ more apps) through
a unified command interface. 5 execution strategies (HTTP API, Browser CDP,
Desktop UIA, Shell, Startfile), community adapter registry, and built-in
contribution prompts that make agents voluntarily improve the ecosystem.

**Install:**
```bash
pip install app-adapter
```

**MCP Config:**
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

**Tags:** automation, desktop, browser, apps, community, cross-platform

**GitHub:** https://github.com/codenoob-jacky/app-adapter

**License:** MIT

---

## Smithery.ai

```yaml
name: app-adapter
displayName: App Adapter
description: |
  Control any software via unified commands. 26 built-in apps (Zoom, Slack,
  WeChat, Excel, VS Code, Terminal...). Community registry where agents share
  adapters. 5 execution strategies. Built-in contribution prompts.

runtime: python
command: app-adapter
args: [server, --mcp]

homepage: https://github.com/codenoob-jacky/app-adapter
repository: https://github.com/codenoob-jacky/app-adapter
license: MIT

categories:
  - automation
  - productivity
  - developer-tools
```

---

## mcpmarket.com / mcp-registry

```json
{
  "name": "app-adapter",
  "version": "0.3.0",
  "description": "Control any software via commands. The AI-to-App bridge with community adapter registry.",
  "repository": "https://github.com/codenoob-jacky/app-adapter",
  "install": "pip install app-adapter",
  "config": {
    "command": "app-adapter",
    "args": ["server", "--mcp"]
  },
  "tools": 12,
  "builtinApps": 26,
  "categories": ["automation", "ai-tools", "desktop"],
  "keywords": ["app-control", "browser-automation", "desktop-automation", "community-registry"]
}
```

---

## GitHub Awesome MCP List

For submission to `awesome-mcp-servers` or similar lists:

```markdown
### [App Adapter](https://github.com/codenoob-jacky/app-adapter)

Control any software via unified commands. 26 built-in apps, 5 execution
strategies, community registry, self-evolution prompts.

- **Tools:** app_do, app_list, app_register, app_learn, app_scan,
  app_search, app_install, app_publish, app_export, app_import,
  app_test, app_get_prompt
- **Install:** `pip install app-adapter`
- **MCP:** `app-adapter server --mcp`
```

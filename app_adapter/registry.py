"""
App Adapter Registry — Community-driven adapter sharing.

Uses the GitHub repo as the registry. No extra infrastructure needed.
- Agents search the registry to find adapters
- Agents install adapters from the registry
- Agents publish adapters back to the community

GitHub repo: https://github.com/codenoob-jacky/app-adapter
Registry folder: registry/*.json
"""
import json, os, sys
from urllib.request import Request, urlopen
from urllib.error import URLError
import ssl

_SSL = ssl.create_default_context()
_SSL.check_hostname = False
_SSL.verify_mode = ssl.CERT_NONE

REGISTRY_REPO = "codenoob-jacky/app-adapter"
REGISTRY_BRANCH = "main"
REGISTRY_PATH = "registry"
RAW_BASE = f"https://raw.githubusercontent.com/{REGISTRY_REPO}/{REGISTRY_BRANCH}/{REGISTRY_PATH}"
API_BASE = f"https://api.github.com/repos/{REGISTRY_REPO}"

# Local cache of registry index
_registry_cache = None
_cache_time = 0


def _get_registry_index() -> list:
    """Fetch list of available adapters from GitHub registry folder."""
    global _registry_cache, _cache_time
    import time
    now = time.time()

    # Use cache for 5 minutes
    if _registry_cache and (now - _cache_time) < 300:
        return _registry_cache

    try:
        url = f"{API_BASE}/contents/{REGISTRY_PATH}?ref={REGISTRY_BRANCH}"
        req = Request(url, headers={"User-Agent": "AppAdapter/1.0", "Accept": "application/vnd.github.v3+json"})
        resp = urlopen(req, timeout=10, context=_SSL)
        data = json.loads(resp.read().decode("utf-8"))
        if isinstance(data, list):
            _registry_cache = [item for item in data if item["name"].endswith(".json")]
            _cache_time = now
            return _registry_cache
    except Exception:
        pass

    # Fallback: return empty if GitHub API unavailable
    if _registry_cache is None:
        _registry_cache = []
    return _registry_cache


def app_search(query: str = "") -> str:
    """Search the community registry for adapters.

    Without query: lists all community adapters available.
    With query: filters by app name or description.

    The registry is a GitHub folder (registry/*.json) containing
    community-contributed adapter definitions.

    Example:
        app_search("slack")  → Find Slack-related adapters
        app_search()         → List all community adapters
    """
    index = _get_registry_index()

    if not index:
        return "[Registry] No community adapters found, or GitHub API is unreachable.\n  The registry lives at: https://github.com/codenoob-jacky/app-adapter/tree/main/registry\n  Be the first to publish! Use app_publish('your_app') to contribute.\n  You can also install adapters shared directly by other agents via app_import()."

    results = []
    for item in index:
        name = item["name"].replace(".json", "")
        if query and query.lower() not in name.lower():
            continue
        results.append(f"  • {name} — {RAW_BASE}/{item['name']}")

    if not results:
        return f"[Registry] No adapters matching '{query}' found.\n  Try a broader search, or be the first to create '{query}':\n    app_register('{query}|||...') → app_learn(...) → app_publish('{query}')"

    lines = [f"[Registry] Found {len(results)} adapter(s) matching '{query}':", ""]
    lines.extend(results)
    lines.append("")
    lines.append("To install: app_install('adapter_name')")
    lines.append("To publish your own: app_publish('your_app_name')")
    return "\n".join(lines)


def app_install(name: str) -> str:
    """Install an adapter from the community registry.

    Downloads the adapter JSON from GitHub and merges it into your local adapters.
    If the adapter already exists, it will be overwritten with the community version.

    Example:
        app_install("slack")    → Download and install Slack adapter
        app_install("discord")  → Download and install Discord adapter
    """
    from .core import app_import

    name = name.strip().lower().replace(".json", "")
    url = f"{RAW_BASE}/{name}.json"

    try:
        req = Request(url, headers={"User-Agent": "AppAdapter/1.0"})
        resp = urlopen(req, timeout=10, context=_SSL)
        data = resp.read().decode("utf-8")

        # Validate it's proper JSON
        parsed = json.loads(data)
        if name not in parsed:
            # The JSON might wrap the adapter differently
            pass

        result = app_import(data, overwrite=True)
        return f"[Install] Downloaded from registry: {url}\n{result}"

    except URLError as e:
        if "404" in str(e) or "403" in str(e):
            return f"[X] Adapter '{name}' not found in the registry.\n  Check available adapters: app_search()\n  Registry URL: {url}"
        return f"[X] Failed to download '{name}': {e}\n  The registry might be unreachable. Try again later."
    except json.JSONDecodeError:
        return f"[X] Corrupted adapter file at {url}\n  Please report this issue to the registry maintainers."
    except Exception as e:
        return f"[X] Install failed: {e}"


def app_publish(app_name: str, message: str = "") -> str:
    """Prepare an adapter for publishing to the community registry.

    This:
    1. Exports the adapter as valid JSON
    2. Validates it has proper structure
    3. Prints instructions for submitting to GitHub
    4. (Future: auto-PR via GitHub API)

    Example:
        app_publish("my_slack_adapter")
        app_publish("spotify|||Added send_playlist action")
    """
    from .core import app_export, ADAPTERS

    # Parse app_name (may include commit message via |||)
    parts = app_name.split("|||", 1)
    name = parts[0].strip().lower()
    msg = parts[1].strip() if len(parts) > 1 else (message or f"Add {name} adapter")

    adapter = ADAPTERS.get(name)
    if not adapter:
        return f"[X] '{name}' not registered locally.\n  Use app_register() to create it first, then app_learn() to teach it actions, then app_test() to verify before publishing."

    # Quality checks
    issues = []
    if len(adapter.get("actions", {})) < 2:
        issues.append("⚠️  Only 1 action — consider adding more via app_learn() before publishing")
    if not adapter.get("url"):
        issues.append("ℹ️  No URL configured — add one for better discoverability")
    if not adapter.get("category"):
        issues.append("ℹ️  No category set — add one (communication, social, productivity, etc.)")

    # Validate each action
    for action_name, action in adapter["actions"].items():
        if "desc" not in action:
            issues.append(f"⚠️  '{action_name}' missing description")
        if "strategy" not in action:
            issues.append(f"⚠️  '{action_name}' missing strategy")

    json_str = app_export(name)
    payload = json.loads(json_str)

    # Add metadata for registry
    payload[name]["_registry"] = {
        "published_by": "agent",
        "version": "1.0.0",
        "message": msg,
    }

    final_json = json.dumps(payload, ensure_ascii=False, indent=2)

    result = [
        f"[Publish] Adapter '{name}' ready for publication.",
        f"  Actions: {len(adapter['actions'])} | Category: {adapter.get('category', 'none')}",
        "",
    ]

    if issues:
        result.append("Quality checks:")
        result.extend(issues)
        result.append("")

    result.append("To publish to the community registry:")
    result.append(f"  1. Save the JSON below as registry/{name}.json")
    result.append(f"  2. Commit: git add registry/{name}.json && git commit -m '{msg}'")
    result.append(f"  3. Push: git push origin main")
    result.append(f"  4. Or create a PR at: https://github.com/{REGISTRY_REPO}/compare")
    result.append("")
    result.append("─── JSON ───")
    result.append(final_json)
    result.append("─── END ───")

    return "\n".join(result)

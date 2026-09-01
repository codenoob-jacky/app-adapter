"""
Real Playwright CDP Executor for browser automation.

Backed by browser_engine (persistent dedicated browser — logins survive).
Optional dependency: playwright — `pip install playwright`.
No `playwright install` needed: we connect to the system browser over CDP.

Commands: navigate, click, click_text, fill, type, upload, press_key,
          read, inspect, check, screenshot, evaluate, get_text,
          fill_then_click, click_then_upload

If Playwright is not available, actions fall back to instruction mode
(telling the agent what to do) rather than failing silently.
"""
import json as _json
import os
import time
from typing import Optional

from .browser_engine import get_page


# ── Page-scan JS: port of voice_agent's web_inspect_area (proven on
#    weibo/zhihu/xiaohongshu). Finds interactive elements + suggested selectors. ──

_INSPECT_JS_TEMPLATE = """(function(){
    var desc = __DESC_JSON__;
    var limit = __LIMIT__;

    var areaKW = desc ? desc.split(/[\\s,，]+/) : [];

    var containers;
    if (!desc || areaKW.length === 0) {
        containers = [document.body];
    } else {
        containers = [];
        var allDivs = document.querySelectorAll('div, section, aside, dialog, [role="dialog"], [class*="dialog"], [class*="picker"], [class*="panel"], [class*="modal"], [class*="popup"]');
        var maxContainers = Math.min(allDivs.length, 200);
        for (var i=0; i<maxContainers; i++) {
            var el = allDivs[i];
            if (!el.offsetParent) continue;
            var txt = (el.innerText||'').substring(0,200).toLowerCase();
            var cls = (el.className||'').toLowerCase();
            var id = (el.id||'').toLowerCase();
            var combined = txt + ' ' + cls + ' ' + id;
            for (var k=0; k<areaKW.length; k++) {
                if (areaKW[k].length >= 2 && combined.indexOf(areaKW[k]) >= 0) {
                    containers.push(el); break;
                }
            }
        }
    }
    if (containers.length === 0) containers = [document.body];
    containers.push(document.body);

    var results = [];
    var seen = new Set();

    function addResult(el, source) {
        if (results.length >= limit) return;
        if (!el || !el.offsetParent) return;
        var tag = el.tagName.toLowerCase();
        var cls = (el.className||'').toString().trim();
        var id = el.id || '';
        var text = (el.innerText||el.textContent||'').trim().substring(0,60).replace(/\\s+/g,' ');
        if (!text) text = (el.title||el.placeholder||el.getAttribute('aria-label')||'');

        var sel = '';
        if (id) sel = '#' + id;
        else if (cls) {
            var classes = cls.split(/\\s+/).filter(function(c){
                if (c.length === 0) return false;
                if (c.startsWith('_') && c.length < 30) return true;
                if (c.length > 40 && /^[a-z0-9_-]+$/.test(c)) return false;
                return true;
            });
            sel = tag + '.' + classes.slice(0,4).join('.');
        }
        else sel = tag;

        var rect = el.getBoundingClientRect();
        if (rect.width < 8 && rect.height < 8) return;

        var key = sel + '|' + text;
        if (seen.has(key)) return;
        seen.add(key);

        results.push({
            tag: tag, class: cls.substring(0,80), id: id,
            text: text.substring(0,60), selector: sel.substring(0,120), source: source
        });
    }

    var maxContainersToScan = desc ? Math.min(containers.length, 3) : 1;
    for (var c=0; c<maxContainersToScan; c++) {
        var container = containers[c];
        var containerName = (container.className||container.id||container.tagName||'').toString().substring(0,40);

        var tas = container.querySelectorAll('textarea, [contenteditable="true"]');
        for (var j=0; j<Math.min(tas.length, 10); j++) { addResult(tas[j], containerName); if (results.length>=limit) break; }

        var inputs = container.querySelectorAll('input:not([type="hidden"])');
        for (var k=0; k<Math.min(inputs.length, 50); k++) { addResult(inputs[k], containerName); if (results.length>=limit) break; }

        var submitWords = ['发布','发表','提交','发送','确定','确认','回答','publish','submit','send','post','save'];
        var allBtns = container.querySelectorAll('button, [role="button"]');
        for (var ib=0; ib<Math.min(allBtns.length, 100); ib++) {
            var t = (allBtns[ib].innerText||'').trim();
            if (submitWords.indexOf(t) >= 0 && allBtns[ib].offsetParent) {
                addResult(allBtns[ib], containerName+'/form');
                if (results.length>=limit) break;
            }
        }
        var actionWords2 = ['发想法','写回答','写文章','提问题','发视频','分享','创建','提问','关注','投稿','新建','上传','编辑','删除','取消'];
        for (var ib2=0; ib2<Math.min(allBtns.length, 100); ib2++) {
            var t2 = (allBtns[ib2].innerText||'').trim();
            if (submitWords.indexOf(t2) >= 0) continue;
            if (actionWords2.indexOf(t2) >= 0 && allBtns[ib2].offsetParent) {
                addResult(allBtns[ib2], containerName);
                if (results.length>=limit) break;
            }
        }
        var links = container.querySelectorAll('a');
        for (var il=0; il<Math.min(links.length, 50); il++) { addResult(links[il], containerName); if (results.length>=limit) break; }

        if (results.length < limit) {
        var clickables = container.querySelectorAll('div[onclick], span[onclick], div[role], span[role], li[class*="item"], [class*="clickable"]');
        for (var k2=0; k2<Math.min(clickables.length, 100); k2++) { addResult(clickables[k2], containerName); if (results.length>=limit) break; }
        }

        if (results.length < limit) {
        var imgs = container.querySelectorAll('img, [style*="background-image"]');
        for (var m=0; m<Math.min(imgs.length, 50); m++) { addResult(imgs[m], containerName); if (results.length>=limit) break; }
        }
    }

    if (results.length === 0) return 'EMPTY: no interactive elements found' + (desc ? ' matching "' + desc + '".' : '. Try leaving description empty for a full page scan.');

    var out = [];
    out.push('Found ' + results.length + ' interactive elements' + (desc ? ' in "' + desc + '"' : '') + ' on page ' + location.href.substring(0,80) + ':');
    for (var r=0; r<results.length; r++) {
        var item = results[r];
        var extra = '';
        var it = (item.text||'').trim();
        if (['发布','发表','提交','发送'].indexOf(it) >= 0) extra = ' [SUBMIT]';
        out.push((r+1) + '. [' + item.tag + '] ' + item.text.substring(0,50) + extra + ' | selector: ' + item.selector + ' | in: ' + item.source);
    }
    return out.join('\\n');
})()"""


class CDPExecutor:
    """Wraps Playwright for real browser automation."""

    def __init__(self):
        self._available = None  # None = not checked yet

    @property
    def available(self) -> bool:
        """Check if Playwright is installed."""
        if self._available is None:
            try:
                from playwright.sync_api import sync_playwright  # noqa: F401
                self._available = True
            except ImportError:
                self._available = False
        return self._available

    # ── Command handlers ──────────────────────────────────────────

    def execute(self, cmd: str, action: dict, params: dict) -> str:
        """Execute a CDP command using Playwright."""
        if not self.available:
            return self._instruction_mode(cmd, action, params)
        try:
            handler = getattr(self, f"_cmd_{cmd}", None)
            if handler is None:
                return f"[X] Unknown cdp_cmd '{cmd}'.\n  Valid: navigate, click, click_text, fill, type, upload, press_key, read, inspect, check, screenshot, evaluate, get_text, fill_then_click, click_then_upload"
            return handler(action, params)
        except Exception as e:
            return self._error_hint(cmd, action, e)

    def _cmd_navigate(self, action, params):
        url = str(params.get("url") or action.get("params", {}).get("url", "") or "").strip()
        if not url:
            return "[X] navigate requires a url parameter.\n  Usage: app_do('browser.open|||url=https://example.com')"
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        page = get_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=15000)
        except Exception:
            pass  # page may still be usable
        try:
            page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            pass
        return f"[CDP ✓] Navigated to {url}\n  Page title: {page.title()}"

    def _cmd_click(self, action, params):
        selector = str(params.get("selector") or action.get("selector", "") or "").strip()
        text = str(params.get("text") or "").strip()
        page = get_page()
        # Try 1: real Playwright click (triggers React/Vue handlers)
        if selector:
            try:
                page.wait_for_selector(selector, state="attached", timeout=5000)
                page.locator(selector).first.click(force=True, timeout=5000)
                return f"[CDP ✓] Clicked '{selector}' (playwright)"
            except Exception:
                pass
        # Try 2: text match (selector may itself be visible text)
        needle = text or selector
        if needle:
            try:
                page.get_by_text(needle, exact=False).first.click(timeout=3000, force=True)
                return f"[CDP ✓] Clicked text '{needle}' (playwright)"
            except Exception:
                pass
        # Try 3: JS click (bypasses visibility/viewport checks)
        if needle:
            try:
                result = page.evaluate(
                    "(function(){"
                    "var els=document.querySelectorAll('button, a, [role=\"button\"], div, span');"
                    "var best=null,bestLen=Infinity;"
                    "for(var i=0;i<els.length;i++){"
                    "var t=(els[i].innerText||'').trim();"
                    "if(t.indexOf(" + _json.dumps(needle) + ")>=0&&els[i].offsetParent){"
                    "if(t.length<bestLen){best=els[i];bestLen=t.length;}}}"
                    "if(best){best.click();return'CLICKED tag='+best.tagName;}"
                    "return'NOT_FOUND';"
                    "})()"
                )
                if str(result).startswith("CLICKED"):
                    return f"[CDP ✓] Clicked text '{needle}' (js)"
            except Exception:
                pass
        return f"[X] Click failed: selector='{selector}' text='{text}' not found.\n  Hint: use browser.inspect first to find the right selector."

    def _cmd_click_text(self, action, params):
        text = str(params.get("text") or action.get("text", "") or "").strip()
        if not text:
            return "[X] click_text requires a text parameter.\n  Usage: app_do('browser.click_text|||text=登录')"
        return self._cmd_click({}, {"text": text})

    def _cmd_fill(self, action, params):
        selector = str(params.get("selector") or action.get("selector", "") or "").strip()
        text = str(params.get("text", params.get("content", "")) or "")
        if not selector:
            return "[X] fill requires a selector parameter.\n  Hint: use browser.inspect first."
        if not text:
            return "[X] fill requires a text parameter."
        page = get_page()
        # Try 1: real fill
        try:
            try:
                page.wait_for_selector(selector, state="visible", timeout=5000)
                page.fill(selector, text)
            except Exception:
                page.locator(selector).first.fill(text, force=True, timeout=5000)
            return f"[CDP ✓] Filled '{selector}' with '{text[:100]}'"
        except Exception:
            pass
        # Try 2: JS direct set + events (React/controlled components)
        try:
            page.evaluate(
                "(function(){"
                "var el=document.querySelector(" + _json.dumps(selector) + ");"
                "if(!el)return'NOT_FOUND';"
                "var tag=el.tagName.toLowerCase();"
                "if(tag==='input'||tag==='textarea'){"
                "el.focus();el.value=" + _json.dumps(text) + ";"
                "el.dispatchEvent(new Event('input',{bubbles:true}));"
                "el.dispatchEvent(new Event('change',{bubbles:true}));"
                "return'FILLED';}"
                "if(el.isContentEditable){"
                "el.focus();el.innerText=" + _json.dumps(text) + ";"
                "el.dispatchEvent(new Event('input',{bubbles:true}));"
                "return'FILLED_CONTENTEDITABLE';}"
                "return'NOT_EDITABLE tag='+tag;"
                "})()"
            )
            return f"[CDP ✓] Filled '{selector}' with '{text[:100]}' (js)"
        except Exception:
            return f"[X] Fill failed on '{selector}'.\n  Hint: the selector may be wrong — use browser.inspect to verify."

    def _cmd_type(self, action, params):
        """Real keyboard typing — use when fill() doesn't register (React, Draft.js, ProseMirror)."""
        selector = str(params.get("selector") or action.get("selector", "") or "").strip()
        text = str(params.get("text", params.get("content", "")) or "")
        if not selector:
            return "[X] type requires a selector parameter.\n  Hint: use browser.inspect first."
        if not text:
            return "[X] type requires a text parameter."
        delay = max(10, min(int(params.get("delay_ms", 50) or 50), 200))
        page = get_page()
        loc = page.locator(selector).first
        loc.click(force=True)
        time.sleep(0.3)
        loc.fill("")
        time.sleep(0.2)
        if hasattr(loc, "press_sequentially"):
            loc.press_sequentially(text, delay=delay)
        else:
            loc.type(text, delay=delay)  # playwright < 1.38
        time.sleep(0.3)
        # Nudge React/Vue state update
        try:
            page.evaluate(
                "(function(){"
                "var el=document.querySelector(" + _json.dumps(selector) + ");"
                "if(el){"
                "el.dispatchEvent(new Event('input',{bubbles:true}));"
                "el.dispatchEvent(new Event('change',{bubbles:true}));"
                "return'OK';}"
                "return'NO_EL';"
                "})()"
            )
        except Exception:
            pass
        return f"[CDP ✓] Typed {len(text)} chars into '{selector}' (real keyboard, delay={delay}ms)"

    def _cmd_upload(self, action, params):
        selector = str(params.get("selector") or action.get("selector", "") or "").strip()
        file_path = str(params.get("file", params.get("path", "")) or "").strip()
        if not file_path:
            return "[X] upload requires a file parameter.\n  Usage: app_do('browser.upload|||file=C:/path/to/img.png')"
        file_path = os.path.expanduser(file_path)
        if not os.path.isfile(file_path):
            return f"[X] File not found: {file_path}"
        page = get_page()
        inp = page.locator(selector) if selector else page.locator('input[type="file"]')
        if inp.count() <= 0:
            # Broader search: first file input of any kind
            inp = page.locator('input[type="file"]')
        if inp.count() <= 0:
            return f"[X] No file input found for selector '{selector or 'input[type=file]'}'.\n  Hint: use browser.inspect to find the upload input."
        inp.first.set_input_files(file_path)
        return f"[CDP ✓] Uploaded '{file_path}' into {selector or 'input[type=file]'}"

    def _cmd_press_key(self, action, params):
        key = str(params.get("key") or action.get("key", "") or "").strip()
        if not key:
            return "[X] press_key requires a key parameter (e.g. Enter, Escape, ArrowDown, Control+a)."
        page = get_page()
        page.keyboard.press(key)
        return f"[CDP ✓] Pressed {key}"

    def _cmd_read(self, action, params):
        page = get_page()
        try:
            text = page.inner_text("body")
        except Exception:
            text = ""
        limit = 8000
        clip = f"\n...[truncated, {len(text)} chars total]" if len(text) > limit else ""
        return f"[CDP ✓] Page: {page.url}\nTitle: {page.title()}\n\n{text[:limit]}{clip}"

    def _cmd_get_text(self, action, params):
        return self._cmd_read(action, params)

    def _cmd_inspect(self, action, params):
        """Scan the DOM for interactive elements + suggested selectors. Look before you click."""
        desc = str(params.get("description", params.get("area", "")) or "").strip()
        try:
            limit = min(max(int(params.get("max_items", 20) or 20), 5), 50)
        except (TypeError, ValueError):
            limit = 20
        page = get_page()
        js = _INSPECT_JS_TEMPLATE.replace("__DESC_JSON__", _json.dumps(desc)).replace("__LIMIT__", str(limit))
        result = page.evaluate(js)
        return f"[CDP ✓] {str(result or 'No results')}"

    def _cmd_check(self, action, params):
        """Verify element state after actions — never assume an action worked."""
        selector = str(params.get("selector") or action.get("selector", "") or "").strip()
        mode = str(params.get("check", "state") or "state").strip().lower()
        if not selector:
            return "[X] check requires a selector parameter."
        page = get_page()
        if mode == "count":
            result = page.evaluate(
                "(function(){return document.querySelectorAll(" + _json.dumps(selector) + ").length;})()"
            )
            return f"[CDP ✓] COUNT: {result} element(s) matching {selector}"
        if mode == "text":
            result = page.evaluate(
                "(function(){"
                "var el=document.querySelector(" + _json.dumps(selector) + ");"
                "if(!el)return'NOT_FOUND';"
                "var txt=el.value||el.innerText||el.textContent||'';"
                "return txt.trim().substring(0,500);"
                "})()"
            )
            return f"[CDP ✓] TEXT of {selector}: {result}"
        result = page.evaluate(
            "(function(){"
            "var el=document.querySelector(" + _json.dumps(selector) + ");"
            "if(!el)return'NOT_FOUND';"
            "var tag=el.tagName.toLowerCase();"
            "var visible=!!el.offsetParent;"
            "var disabled=el.disabled||(el.className||'').indexOf('disabled')>=0;"
            "var txt=(el.value||el.innerText||'').trim().substring(0,40);"
            "return'FOUND tag='+tag+' visible='+visible+' disabled='+disabled+' text=\"'+txt+'\"';"
            "})()"
        )
        return f"[CDP ✓] {str(result or 'UNKNOWN')}"

    def _cmd_screenshot(self, action, params):
        page = get_page()
        path = str(params.get("path", "screenshot.png") or "screenshot.png")
        full = str(params.get("full", "false")).lower() in ("1", "true", "yes")
        page.screenshot(path=path, full_page=full)
        return f"[CDP ✓] Screenshot saved to '{os.path.abspath(path)}'"

    def _cmd_evaluate(self, action, params):
        js = str(params.get("js") or action.get("js", "") or "").strip()
        if not js:
            return "[X] evaluate requires a js parameter.\n  Usage: app_do('browser.evaluate|||js=document.title')"
        page = get_page()
        result = page.evaluate(js)
        return f"[CDP ✓] JS result: {str(result)[:2000]}"

    def _cmd_fill_then_click(self, action, params):
        selector = str(action.get("selector", "") or "").strip()
        fill_sel = str(action.get("fill_selector", selector) or params.get("fill_selector", "") or "").strip()
        click_sel = str(action.get("click_selector", "") or params.get("click_selector", "") or "").strip()
        text = str(params.get("text", params.get("content", "")) or "")
        page = get_page()
        if not fill_sel:
            return "[X] fill_then_click needs fill_selector (+optional click_selector) in the action config.\n  Fix: app_learn('app|||action|||desc|||cdp|||fill_selector|||fill_then_click') — or use browser.fill then browser.click."
        if not text:
            return "[X] fill_then_click requires a text parameter."
        self._cmd_fill({}, {"selector": fill_sel, "text": text})
        if click_sel:
            try:
                page.locator(click_sel).first.click(force=True, timeout=5000)
                return f"[CDP ✓] Filled '{fill_sel}' and clicked '{click_sel}'."
            except Exception:
                pass
        else:
            page.keyboard.press("Enter")
            return f"[CDP ✓] Filled '{fill_sel}' and pressed Enter."
        # click failed → JS fallback
        try:
            page.evaluate(
                "document.querySelector(" + _json.dumps(click_sel) + ").click();'done'"
            )
            return f"[CDP ✓] Filled '{fill_sel}' and clicked '{click_sel}' (js)."
        except Exception:
            return f"[X] Filled '{fill_sel}' but click on '{click_sel}' failed.\n  Hint: verify the selector with browser.check."

    def _cmd_click_then_upload(self, action, params):
        selector = str(params.get("selector") or action.get("selector", "") or "").strip()
        file_path = str(params.get("file", params.get("path", "")) or "").strip()
        if not selector:
            return "[X] click_then_upload requires a selector parameter."
        page = get_page()
        if not file_path:
            page.locator(selector).first.click(force=True)
            return f"[CDP ✓] Clicked '{selector}' — no file provided, select it manually."
        file_path = os.path.expanduser(file_path)
        if not os.path.isfile(file_path):
            return f"[X] File not found: {file_path}"
        with page.expect_file_chooser() as fc_info:
            page.locator(selector).first.click(force=True)
        fc_info.value.set_files(file_path)
        return f"[CDP ✓] Clicked '{selector}' and uploaded '{file_path}'"

    # ── Fallbacks ─────────────────────────────────────────────────

    def _error_hint(self, cmd, action, e):
        error_msg = str(e)[:300]
        if "No Chromium-based browser found" in error_msg or "debug port" in error_msg:
            return f"[CDP ✗] Browser launch failed: {error_msg}\n  Hint: set APP_ADAPTER_BROWSER_CMD to your browser path."
        if "net::ERR_" in error_msg:
            return f"[CDP ✗] Network error: {error_msg}\n  Hint: check the URL and network connection."
        if "timeout" in error_msg.lower():
            return f"[CDP ✗] Timed out: {error_msg[:200]}\n  Hint: element may not exist yet or selector is wrong — use browser.inspect to verify."
        return f"[CDP ✗] {error_msg}"

    def _instruction_mode(self, cmd: str, action: dict, params: dict) -> str:
        """Fallback: tell the agent what to do (Playwright not installed)."""
        selector = action.get("selector", "")
        text = params.get("text", params.get("content", ""))
        url = params.get("url") or action.get("params", {}).get("url", "")
        hints = {
            "navigate": f"Open browser and go to: {url or '(no URL configured)'}",
            "click": f"Find and click element: '{selector or text}'",
            "click_text": f"Click the element showing text: '{text}'",
            "fill": f"Type '{str(text)[:100]}' into: '{selector}'",
            "type": f"Type '{str(text)[:100]}' into: '{selector}' (real keyboard)",
            "upload": f"Upload file into: '{selector or 'file input'}'",
            "press_key": f"Press key: {params.get('key', '?')}",
            "read": "Read the visible text of the page",
            "inspect": "Scan the page for interactive elements and selectors",
            "check": f"Check element state: '{selector}'",
            "screenshot": "Take a screenshot of the current page",
            "evaluate": f"Run in console: {str(action.get('js', ''))[:200]}",
            "get_text": "Extract all text content from the page",
            "fill_then_click": "Fill the form field, then click submit",
            "click_then_upload": f"Click '{selector}', then select file to upload",
        }
        instruction = hints.get(cmd, f"Execute CDP command: {cmd}")
        return f"[CDP] {instruction}\n  Install Playwright for real automation: pip install playwright"


# Singleton
_cdp_executor: Optional[CDPExecutor] = None


def get_cdp_executor() -> CDPExecutor:
    global _cdp_executor
    if _cdp_executor is None:
        _cdp_executor = CDPExecutor()
    return _cdp_executor

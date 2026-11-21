"""Find the Microsoft Learn page that best matches a question.

Practice Mode and the review page link each question to Microsoft Learn. A search
link always works but lands on a results list. This module asks Microsoft Learn for
the top matching page, so the link opens the article itself.

Order of attempts, first success wins:
  1. Microsoft Learn site search API
  2. Microsoft Learn MCP server (microsoft_docs_search tool)
  3. A Learn search link (the old behaviour), so a lookup problem never breaks the app

Results are cached in memory and in doc_links.json, so each topic is looked up once.
"""
import json
import os
import threading
import time
from pathlib import Path
from urllib.parse import quote, urlparse

import httpx

LEARN = "https://learn.microsoft.com"
TIMEOUT = float(os.environ.get("SC500_DOC_TIMEOUT", "6"))
SKIP_PATHS = ("/answers/", "/shows/", "/users/", "/search/", "/api/")  # Q&A, videos, profiles

_lock = threading.Lock()
_cache: dict[str, dict] = {}
_cache_file: Path | None = None
_failed: dict[str, float] = {}   # term -> time of the last failed lookup
RETRY_AFTER = 600                # seconds before a failed term is looked up again


def init(data_dir: Path):
    """Load the cache from disk. Call once at start-up."""
    global _cache_file
    _cache_file = data_dir / "doc_links.json"
    if _cache_file.exists():
        try:
            _cache.update(json.loads(_cache_file.read_text(encoding="utf-8")))
        except ValueError:
            pass


def search_link(term: str) -> dict:
    return {"label": term, "url": f"{LEARN}/en-us/search/?terms={quote(term)}", "exact": False}


def _good(url: str) -> bool:
    if not url:
        return False
    p = urlparse(url if url.startswith("http") else LEARN + url)
    return p.scheme == "https" and p.netloc == "learn.microsoft.com" and not any(s in p.path for s in SKIP_PATHS)


def _absolute(url: str) -> str:
    url = url if url.startswith("http") else LEARN + url
    return url.split("#")[0]


def _pick(items: list[dict], url_keys: tuple, title_keys: tuple) -> dict | None:
    """First usable page, preferring docs over training modules."""
    found = []
    for it in items:
        if not isinstance(it, dict):
            continue
        url = next((it[k] for k in url_keys if isinstance(it.get(k), str)), "")
        title = next((it[k] for k in title_keys if isinstance(it.get(k), str)), "")
        if _good(url):
            found.append({"label": title.strip() or url, "url": _absolute(url), "exact": True})
    docs = [f for f in found if "/training/" not in f["url"]]
    return (docs or found or [None])[0]


def _via_search_api(term: str) -> dict | None:
    r = httpx.get(f"{LEARN}/api/search", timeout=TIMEOUT,
                  params={"search": term, "locale": "en-us", "$top": 10},
                  headers={"Accept": "application/json", "User-Agent": "sc500-exam-simulator"})
    r.raise_for_status()
    data = r.json()
    items = (data.get("results") or data.get("value") or []) if isinstance(data, dict) else []
    return _pick(items, ("url", "link", "contentUrl"), ("title", "displayName"))


def _mcp_json(resp: httpx.Response) -> dict:
    """MCP replies are plain JSON or a server-sent event stream."""
    if "text/event-stream" in resp.headers.get("content-type", ""):
        for line in resp.text.splitlines():
            if line.startswith("data:"):
                return json.loads(line[5:].strip())
        return {}
    return resp.json()


def _via_mcp(term: str) -> dict | None:
    url = f"{LEARN}/api/mcp"
    h = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
    with httpx.Client(timeout=TIMEOUT, headers=h) as c:
        init = c.post(url, json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2025-03-26", "capabilities": {},
            "clientInfo": {"name": "sc500-exam-simulator", "version": "1.0"}}})
        init.raise_for_status()
        sid = init.headers.get("mcp-session-id")
        if sid:
            c.headers["mcp-session-id"] = sid
        c.post(url, json={"jsonrpc": "2.0", "method": "notifications/initialized"})
        r = c.post(url, json={"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                              "params": {"name": "microsoft_docs_search", "arguments": {"query": term}}})
        r.raise_for_status()
        result = _mcp_json(r).get("result", {})
    for block in result.get("content", []):
        if block.get("type") == "text":
            try:
                payload = json.loads(block["text"])
            except ValueError:
                continue
            items = payload.get("results", []) if isinstance(payload, dict) else payload
            hit = _pick(items, ("contentUrl", "url", "link"), ("title",))
            if hit:
                return hit
    return None


def resolve(term: str) -> dict:
    """Return {label, url, exact}. exact is False when it fell back to a search link."""
    term = (term or "").strip()[:120]
    if not term:
        return search_link("SC-500")
    with _lock:
        if term in _cache:
            return _cache[term]
        if time.time() - _failed.get(term, 0) < RETRY_AFTER:
            return search_link(term)  # failed a moment ago: don't make the page wait again
    hit = None
    for lookup in (_via_search_api, _via_mcp):
        try:
            hit = lookup(term)
        except Exception as exc:  # network, HTTP or parse error: try the next one
            print(f"  [docs] {lookup.__name__} failed for '{term}': {type(exc).__name__}: {exc}", flush=True)
        if hit:
            break
    if not hit:
        with _lock:
            _failed[term] = time.time()  # retried after RETRY_AFTER, not cached for good
        return search_link(term)
    with _lock:
        _cache[term] = hit
        if _cache_file:
            try:
                _cache_file.write_text(json.dumps(_cache), encoding="utf-8")
            except OSError:
                pass
    return hit

"""Web search tool — search the internet via DuckDuckGo HTML (no API key required).

Falls back gracefully when network is unavailable.  Results are stripped
to title + snippet + URL to keep token usage low.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any
from html import unescape
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.parse import quote_plus

from butler.env_parse import env_truthy

logger = logging.getLogger(__name__)


def web_search_enabled() -> bool:
    return env_truthy("BUTLER_ENABLE_WEB_SEARCH", default=False)


def _timeout() -> float:
    try:
        return max(3.0, float(os.getenv("BUTLER_WEB_SEARCH_TIMEOUT", "") or "15"))
    except ValueError:
        return 15.0


def _search_duckduckgo(query: str, max_results: int = 5) -> list[dict[str, str]]:
    """Search DuckDuckGo HTML and parse results."""
    url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
    req = Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; Butler/1.0)",
        "Accept": "text/html",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    })
    try:
        with urlopen(req, timeout=_timeout()) as resp:
            html = resp.read(200_000).decode("utf-8", errors="replace")
    except (HTTPError, URLError, OSError) as exc:
        logger.warning("DuckDuckGo search failed: %s", exc)
        return []

    results: list[dict[str, str]] = []
    # DuckDuckGo HTML results pattern
    blocks = re.findall(
        r'<a[^>]+class="result__a"[^>]+href="([^"]*)"[^>]*>(.*?)</a>.*?'
        r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>',
        html,
        re.DOTALL,
    )
    for href, title_html, snippet_html in blocks[:max_results]:
        title = re.sub(r"<[^>]+>", "", title_html).strip()
        title = unescape(title)
        snippet = re.sub(r"<[^>]+>", "", snippet_html).strip()
        snippet = unescape(snippet)
        # DuckDuckGo wraps URLs in redirect; extract actual URL
        actual_url = href
        ud_match = re.search(r"uddg=([^&]+)", href)
        if ud_match:
            from urllib.parse import unquote
            actual_url = unquote(ud_match.group(1))
        if title and actual_url:
            results.append({
                "title": title,
                "snippet": snippet[:300],
                "url": actual_url,
            })
    return results


def tool_web_search(query: str = "", max_results: int = 5, **_: Any) -> str:
    """Search the web and return structured results."""
    if not web_search_enabled():
        return json.dumps({
            "error": "web_search disabled",
            "hint": "设置 BUTLER_ENABLE_WEB_SEARCH=1 启用，或使用 /config set BUTLER_ENABLE_WEB_SEARCH 1",
        })

    q = (query or "").strip()
    if not q:
        return json.dumps({"error": "query is required"})

    cap = max(1, min(10, int(max_results or 5)))
    results = _search_duckduckgo(q, max_results=cap)

    if not results:
        return json.dumps({
            "ok": True,
            "query": q,
            "results": [],
            "message": "No results found or search service unavailable",
        })

    return json.dumps({
        "ok": True,
        "query": q,
        "count": len(results),
        "results": results,
    }, ensure_ascii=False)


def register_web_search_tool(register_fn) -> None:
    register_fn(
        name="web_search",
        description=(
            "Search the web for information using a keyword query. "
            "Returns titles, snippets and URLs. Use this before web_fetch "
            "when you need to find relevant pages."
        ),
        schema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query (keywords or question)",
                },
                "max_results": {
                    "type": "integer",
                    "default": 5,
                    "minimum": 1,
                    "maximum": 10,
                    "description": "Maximum number of results to return",
                },
            },
            "required": ["query"],
        },
        handler=tool_web_search,
        toolset="network",
    )


__all__ = ["register_web_search_tool", "tool_web_search", "web_search_enabled"]

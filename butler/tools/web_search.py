"""Web search tool — DuckDuckGo HTML POST + API fallback (no API key)."""

from __future__ import annotations

import json
import logging
import re
from html import unescape
from typing import Any
from urllib.parse import quote_plus, unquote

from butler.env_parse import env_truthy, float_env, int_env

logger = logging.getLogger(__name__)

_DDG_HTML_URL = "https://html.duckduckgo.com/html/"
_DDG_API_URL = "https://api.duckduckgo.com/"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/json",
    "Accept-Language": "zh-CN,zh;q=0.9,en-US,en;q=0.8",
}


def web_search_enabled() -> bool:
    return env_truthy("BUTLER_ENABLE_WEB_SEARCH", default=False)


def _timeout() -> float:
    try:
        return max(3.0, float_env("BUTLER_WEB_SEARCH_TIMEOUT", 15))
    except ValueError:
        return 15.0


def _max_retries() -> int:
    try:
        return max(1, int_env("BUTLER_WEB_SEARCH_RETRIES", 2, min=1))
    except ValueError:
        return 2


def _unwrap_ddg_href(href: str) -> str:
    raw = str(href or "").strip()
    match = re.search(r"uddg=([^&]+)", raw)
    if match:
        return unquote(match.group(1))
    return raw


def _strip_html(text: str) -> str:
    return unescape(re.sub(r"<[^>]+>", "", text or "").strip())


def parse_ddg_html_results(html: str, max_results: int) -> list[dict[str, str]]:
    """Parse DuckDuckGo HTML SERP into title/snippet/url rows."""
    cap = max(1, max_results)
    results: list[dict[str, str]] = []
    seen: set[str] = set()

    blocks = re.findall(
        r'<a[^>]+class="result__a"[^>]+href="([^"]*)"[^>]*>(.*?)</a>.*?'
        r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>',
        html,
        re.DOTALL | re.IGNORECASE,
    )
    for href, title_html, snippet_html in blocks:
        url = _unwrap_ddg_href(href)
        title = _strip_html(title_html)
        if not title or not url or url in seen:
            continue
        seen.add(url)
        results.append({
            "title": title,
            "snippet": _strip_html(snippet_html)[:300],
            "url": url,
        })
        if len(results) >= cap:
            return results

    # Lite / alternate markup fallback.
    for href, title_html in re.findall(
        r'<a[^>]+rel="nofollow"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
        html,
        re.DOTALL | re.IGNORECASE,
    ):
        url = _unwrap_ddg_href(href)
        title = _strip_html(title_html)
        if not title or not url.startswith("http") or url in seen:
            continue
        seen.add(url)
        results.append({"title": title, "snippet": "", "url": url})
        if len(results) >= cap:
            break
    return results


def _parse_ddg_api_payload(payload: dict[str, Any], max_results: int) -> list[dict[str, str]]:
    cap = max(1, max_results)
    results: list[dict[str, str]] = []
    seen: set[str] = set()

    def _add(text: str, url: str) -> None:
        if len(results) >= cap or not url or url in seen:
            return
        seen.add(url)
        results.append({
            "title": (text or url)[:200],
            "snippet": (text or "")[:300],
            "url": url,
        })

    abstract = str(payload.get("AbstractURL") or "").strip()
    abstract_text = str(payload.get("AbstractText") or payload.get("Abstract") or "").strip()
    if abstract:
        _add(abstract_text or abstract, abstract)

    related = payload.get("RelatedTopics") or []
    if isinstance(related, list):
        for item in related:
            if not isinstance(item, dict):
                continue
            topics = item.get("Topics")
            if isinstance(topics, list):
                for sub in topics:
                    if not isinstance(sub, dict):
                        continue
                    _add(str(sub.get("Text") or ""), str(sub.get("FirstURL") or ""))
            else:
                _add(str(item.get("Text") or ""), str(item.get("FirstURL") or ""))
    return results


def _fetch_with_httpx(
    method: str,
    url: str,
    *,
    trust_env: bool,
    data: dict[str, str] | None = None,
) -> str:
    import httpx

    timeout = _timeout()
    with httpx.Client(
        timeout=timeout,
        follow_redirects=True,
        trust_env=trust_env,
        headers=_HEADERS,
    ) as client:
        if method == "post":
            resp = client.post(url, data=data or {})
        else:
            resp = client.get(url)
        resp.raise_for_status()
        return resp.text


def _search_ddg_html_post(query: str, max_results: int, *, trust_env: bool) -> list[dict[str, str]]:
    html = _fetch_with_httpx(
        "post",
        _DDG_HTML_URL,
        trust_env=trust_env,
        data={"q": query},
    )
    return parse_ddg_html_results(html, max_results)


def _search_ddg_api(query: str, max_results: int, *, trust_env: bool) -> list[dict[str, str]]:
    url = (
        f"{_DDG_API_URL}?q={quote_plus(query)}"
        "&format=json&no_html=1&no_redirect=1&skip_disambig=1"
    )
    text = _fetch_with_httpx("get", url, trust_env=trust_env)
    payload = json.loads(text)
    if not isinstance(payload, dict):
        return []
    return _parse_ddg_api_payload(payload, max_results)


def _search_duckduckgo(query: str, max_results: int = 5) -> list[dict[str, str]]:
    """Try DDG HTML POST then instant-answer API; alternate trust_env for proxy TLS."""
    q = str(query or "").strip()
    if not q:
        return []

    strategies: list[tuple[str, bool]] = [
        ("html_post", True),
        ("html_post", False),
        ("api", True),
        ("api", False),
    ]
    retries = _max_retries()
    last_exc: Exception | None = None

    for attempt in range(retries):
        for kind, trust_env in strategies:
            try:
                if kind == "html_post":
                    rows = _search_ddg_html_post(q, max_results, trust_env=trust_env)
                else:
                    rows = _search_ddg_api(q, max_results, trust_env=trust_env)
                if rows:
                    return rows[:max_results]
            except Exception as exc:
                last_exc = exc
                logger.warning(
                    "DuckDuckGo %s trust_env=%s attempt=%s failed: %s",
                    kind,
                    trust_env,
                    attempt + 1,
                    exc,
                )
    if last_exc is not None:
        logger.warning("DuckDuckGo search exhausted for %r: %s", q[:80], last_exc)
    return []


def tool_web_search(query: str = "", max_results: int = 5, **_: Any) -> str:
    """Search the web and return structured results."""
    if not web_search_enabled():
        return json.dumps({
            "error": "web_search disabled",
            "hint": "设置 BUTLER_ENABLE_WEB_SEARCH=1 启用，或使用 /config set BUTLER_ENABLE_WEB_SEARCH 1",
        }, ensure_ascii=False)

    q = (query or "").strip()
    if not q:
        return json.dumps({"error": "query is required"}, ensure_ascii=False)

    cap = max(1, min(10, int(max_results or 5)))
    results = _search_duckduckgo(q, max_results=cap)

    if not results:
        return json.dumps({
            "ok": True,
            "query": q,
            "results": [],
            "message": "No results found or search service unavailable",
            "hint": (
                "DuckDuckGo 不可达或零结果；可改用 mcp_firecrawl_firecrawl_search / "
                "mcp_firecrawl_scrape，勿重复空搜 web_search。"
            ),
        }, ensure_ascii=False)

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


__all__ = [
    "parse_ddg_html_results",
    "register_web_search_tool",
    "tool_web_search",
    "web_search_enabled",
    "_search_duckduckgo",
]

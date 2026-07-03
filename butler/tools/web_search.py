"""Web search tool — DuckDuckGo HTML POST + API fallback (no API key)."""

from __future__ import annotations

import json
import logging
import os
import re
import time
from html import unescape
from typing import Any
from urllib.parse import quote_plus, unquote

from butler.env_parse import env_truthy, float_env, int_env

logger = logging.getLogger(__name__)

_BUDGET_MAX_SEC = 300.0
_PER_ATTEMPT_TIMEOUT_MAX_SEC = 30.0

_DDG_HTML_URL = "https://html.duckduckgo.com/html/"
_DDG_LITE_URL = "https://lite.duckduckgo.com/lite/"
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


def _per_attempt_timeout_cap() -> float:
    try:
        raw = float_env("BUTLER_WEB_SEARCH_TIMEOUT", 15)
        return min(_PER_ATTEMPT_TIMEOUT_MAX_SEC, max(3.0, raw))
    except ValueError:
        return 15.0


def _total_budget() -> float:
    try:
        raw = float_env("BUTLER_WEB_SEARCH_BUDGET", 60)
        return min(_BUDGET_MAX_SEC, max(5.0, raw))
    except ValueError:
        return 60.0


def _proxy_configured() -> bool:
    for key in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
    ):
        if str(os.environ.get(key) or "").strip():
            return True
    return False


def _try_direct_with_proxy() -> bool:
    """When proxy env is set, skip direct attempts unless explicitly enabled."""
    if not _proxy_configured():
        return True
    return env_truthy("BUTLER_WEB_SEARCH_TRY_DIRECT", default=False)


def _search_strategies() -> list[tuple[str, bool]]:
    """Return (kind, trust_env). Proxy-only hosts skip direct to preserve budget."""
    kinds = ("html_post", "html_lite", "api")
    if _proxy_configured() and not _try_direct_with_proxy():
        return [(kind, True) for kind in kinds]
    if _proxy_configured():
        return [(kind, False) for kind in kinds] + [(kind, True) for kind in kinds]
    return [(kind, True) for kind in kinds] + [(kind, False) for kind in kinds]


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
    timeout: float,
    data: dict[str, str] | None = None,
) -> str:
    import httpx

    per = max(3.0, timeout)
    connect_cap = 5.0 if trust_env else 3.0
    timeouts = httpx.Timeout(
        connect=min(connect_cap, per),
        read=per,
        write=min(10.0, per),
        pool=min(5.0, per),
    )
    with httpx.Client(
        timeout=timeouts,
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


def _search_ddg_html_post(
    query: str,
    max_results: int,
    *,
    trust_env: bool,
    timeout: float,
) -> list[dict[str, str]]:
    html = _fetch_with_httpx(
        "post",
        _DDG_HTML_URL,
        trust_env=trust_env,
        timeout=timeout,
        data={"q": query},
    )
    return parse_ddg_html_results(html, max_results)


def _search_ddg_api(
    query: str,
    max_results: int,
    *,
    trust_env: bool,
    timeout: float,
) -> list[dict[str, str]]:
    url = (
        f"{_DDG_API_URL}?q={quote_plus(query)}"
        "&format=json&no_html=1&no_redirect=1&skip_disambig=1"
    )
    text = _fetch_with_httpx("get", url, trust_env=trust_env, timeout=timeout)
    payload = json.loads(text)
    if not isinstance(payload, dict):
        return []
    return _parse_ddg_api_payload(payload, max_results)


def _search_ddg_lite_get(
    query: str,
    max_results: int,
    *,
    trust_env: bool,
    timeout: float,
) -> list[dict[str, str]]:
    url = f"{_DDG_LITE_URL}?q={quote_plus(query)}"
    html = _fetch_with_httpx("get", url, trust_env=trust_env, timeout=timeout)
    return parse_ddg_html_results(html, max_results)


def _search_duckduckgo(query: str, max_results: int = 5) -> list[dict[str, str]]:
    """Try DDG backends within a total time budget; direct-first when proxy env is set."""
    q = str(query or "").strip()
    if not q:
        return []

    budget = _total_budget()
    deadline = time.monotonic() + budget
    strategies = _search_strategies()
    max_rounds = _max_retries()
    round_idx = 0

    from butler.tools.web_search_ops import try_search_attempt_safe

    while time.monotonic() < deadline and round_idx < max_rounds:
        round_idx += 1
        for kind, trust_env in strategies:
            remaining = deadline - time.monotonic()
            if remaining < 2.5:
                break
            per_timeout = min(_per_attempt_timeout_cap(), max(3.0, remaining))

            def _run(
                _kind: str = kind,
                _trust_env: bool = trust_env,
                _timeout: float = per_timeout,
            ) -> list[dict[str, str]]:
                if _kind == "html_post":
                    return _search_ddg_html_post(
                        q,
                        max_results,
                        trust_env=_trust_env,
                        timeout=_timeout,
                    )
                if _kind == "html_lite":
                    return _search_ddg_lite_get(
                        q,
                        max_results,
                        trust_env=_trust_env,
                        timeout=_timeout,
                    )
                return _search_ddg_api(
                    q,
                    max_results,
                    trust_env=_trust_env,
                    timeout=_timeout,
                )

            rows = try_search_attempt_safe(
                _run,
                kind=kind,
                trust_env=trust_env,
                round_idx=round_idx,
                query=q,
            )
            if rows:
                return rows[:max_results]
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
    started = time.monotonic()
    results = _search_duckduckgo(q, max_results=cap)
    elapsed = round(time.monotonic() - started, 2)

    if not results:
        return json.dumps({
            "ok": True,
            "query": q,
            "results": [],
            "elapsed_seconds": elapsed,
            "budget_seconds": _total_budget(),
            "message": "No results found or search service unavailable",
            "hint": (
                "DuckDuckGo 不可达或零结果（已用尽本轮 web_search 时间预算）。"
                "下一步：1) mcp_firecrawl_firecrawl_search 取 URL；"
                "2) 对命中 URL 用 mcp_firecrawl_scrape 读正文；"
                "3) 直接总结并附完整 https 来源。勿重复 web_search，勿调 feedback/agent。"
            ),
            "fallback": "firecrawl_search_then_scrape",
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
    "_proxy_configured",
    "_search_duckduckgo",
    "_search_strategies",
    "_total_budget",
    "_try_direct_with_proxy",
]

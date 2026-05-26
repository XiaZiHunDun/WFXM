"""Thin web fetch tool (Firecrawl safeFetch subset, stdlib + url_safety)."""

from __future__ import annotations

import json
import os
import re
from html import unescape
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from butler.env_parse import env_truthy


def web_fetch_enabled() -> bool:
    return env_truthy("BUTLER_ENABLE_WEB_FETCH", default=False)


def _max_bytes() -> int:
    try:
        return max(4096, int(os.getenv("BUTLER_WEB_FETCH_MAX_BYTES", "") or "65536"))
    except ValueError:
        return 65536


def _timeout_seconds() -> float:
    try:
        return max(3.0, float(os.getenv("BUTLER_WEB_FETCH_TIMEOUT", "") or "20"))
    except ValueError:
        return 20.0


def _strip_html_regex(html: str) -> str:
    """Fallback HTML stripping with regex (used when trafilatura is unavailable)."""
    text = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", html)
    text = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _extract_with_trafilatura(html: str, url: str = "") -> dict[str, str] | None:
    """Extract main content with trafilatura; returns None if unavailable."""
    try:
        import trafilatura  # type: ignore[import-untyped]
    except ImportError:
        return None
    try:
        text = trafilatura.extract(
            html,
            url=url or None,
            output_format="txt",
            include_comments=False,
            include_tables=True,
            include_links=True,
        )
        if not text:
            return None
        metadata = trafilatura.extract_metadata(html, default_url=url or None)
        meta: dict[str, str] = {}
        if metadata:
            if getattr(metadata, "title", None):
                meta["title"] = str(metadata.title)
            if getattr(metadata, "author", None):
                meta["author"] = str(metadata.author)
            if getattr(metadata, "date", None):
                meta["date"] = str(metadata.date)
        return {"text": text, **meta}
    except Exception:
        return None


def _strip_html(html: str, *, url: str = "") -> str | dict[str, str]:
    """Extract content from HTML; prefers trafilatura, falls back to regex."""
    result = _extract_with_trafilatura(html, url=url)
    if result is not None:
        return result
    return _strip_html_regex(html)


def tool_web_fetch(url: str, *, max_chars: int = 8000, **_: Any) -> str:
    if not web_fetch_enabled():
        return json.dumps({
            "error": "web_fetch disabled",
            "hint": "设置 BUTLER_ENABLE_WEB_FETCH=1 或改用 MCP/Firecrawl",
        })
    from butler.registry.url_safety import is_safe_url

    target = str(url or "").strip()
    if not target:
        return json.dumps({"error": "url required"})
    if not is_safe_url(target):
        return json.dumps({"error": "URL 未通过安全校验（私网/非法主机）"})
    cap = max(500, min(32_000, int(max_chars or 8000)))
    req = Request(
        target,
        headers={"User-Agent": "Butler-web-fetch/1.0", "Accept": "text/html,application/json,*/*"},
    )
    try:
        with urlopen(req, timeout=_timeout_seconds()) as resp:
            raw = resp.read(_max_bytes() + 1)
            ctype = str(resp.headers.get("Content-Type") or "")
    except HTTPError as exc:
        return json.dumps({"error": f"HTTP {exc.code}", "url": target})
    except URLError as exc:
        return json.dumps({"error": str(exc.reason or exc), "url": target})
    except Exception as exc:
        return json.dumps({"error": str(exc), "url": target})

    if len(raw) > _max_bytes():
        raw = raw[:_max_bytes()]
        truncated = True
    else:
        truncated = False

    decoded = raw.decode("utf-8", errors="replace")
    extra_meta: dict[str, str] = {}

    if "html" in ctype.lower():
        extracted = _strip_html(decoded, url=target)
        if isinstance(extracted, dict):
            body = extracted.pop("text", decoded)
            extra_meta = extracted
        else:
            body = extracted
    else:
        body = decoded

    if len(body) > cap:
        body = body[:cap] + "\n…(truncated)"
    result = {
        "ok": True,
        "url": target,
        "content_type": ctype,
        "truncated": truncated,
        "chars": len(body),
        "text": body,
    }
    if extra_meta:
        result["metadata"] = extra_meta
    return json.dumps(result, ensure_ascii=False)


def register_web_fetch_tool(register_fn) -> None:
    register_fn(
        name="web_fetch",
        description=(
            "Fetch a public HTTP(S) URL as text (HTML stripped). "
            "When NOT to use: private IPs, file://, or when Firecrawl MCP is configured."
        ),
        schema={
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Public https URL"},
                "max_chars": {"type": "integer", "default": 8000, "minimum": 500, "maximum": 32000},
            },
            "required": ["url"],
        },
        handler=tool_web_fetch,
        toolset="network",
    )


__all__ = ["register_web_fetch_tool", "tool_web_fetch", "web_fetch_enabled"]

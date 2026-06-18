"""Per-turn dedup for Firecrawl scrape (avoid double billing in one user turn)."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator
from urllib.parse import urlparse, urlunparse

_urls: ContextVar[set[str] | None] = ContextVar("mcp_turn_scrape_urls", default=None)


def is_firecrawl_scrape_tool(tool_name: str) -> bool:
    name = str(tool_name or "").lower()
    return "firecrawl" in name and name.endswith("scrape")


def normalize_scrape_url(url: str) -> str:
    raw = str(url or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw)
    scheme = (parsed.scheme or "https").lower()
    netloc = (parsed.netloc or "").lower()
    path = parsed.path or "/"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    return urlunparse((scheme, netloc, path, "", parsed.query, ""))


@contextmanager
def turn_scrape_dedup_scope() -> Iterator[None]:
    token = _urls.set(set())
    try:
        yield
    finally:
        _urls.reset(token)


def scrape_url_from_args(args: dict) -> str:
    if not isinstance(args, dict):
        return ""
    for key in ("url", "URL", "target_url", "page_url"):
        val = args.get(key)
        if val:
            return str(val)
    return ""


def check_and_record_scrape(url: str) -> str | None:
    """Return user-facing error if URL already scraped this turn; else record."""
    norm = normalize_scrape_url(url)
    if not norm:
        return None
    bucket = _urls.get()
    if bucket is None:
        bucket = set()
        _urls.set(bucket)
    if norm in bucket:
        return (
            f"同一轮已抓取过 {norm}，请勿重复调用 scrape；"
            "请根据上一轮工具结果直接总结。"
        )
    bucket.add(norm)
    return None


__all__ = [
    "check_and_record_scrape",
    "is_firecrawl_scrape_tool",
    "normalize_scrape_url",
    "scrape_url_from_args",
    "turn_scrape_dedup_scope",
]

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


def _bridge_bucket() -> set[str] | None:
    try:
        from butler.execution_context import get_current_turn_bridge

        bridge = get_current_turn_bridge()
        if bridge is None:
            return None
        bucket = getattr(bridge, "scrape_urls_seen", None)
        if bucket is None:
            bridge.scrape_urls_seen = set()
            bucket = bridge.scrape_urls_seen
        return bucket
    except Exception:
        return None


def check_and_record_scrape(url: str) -> str | None:
    """Return user-facing error if URL already scraped this turn; else record."""
    norm = normalize_scrape_url(url)
    if not norm:
        return None

    buckets: list[set[str]] = []
    bridge_bucket = _bridge_bucket()
    if bridge_bucket is not None:
        buckets.append(bridge_bucket)
    ctx_bucket = _urls.get()
    if ctx_bucket is not None and ctx_bucket is not bridge_bucket:
        buckets.append(ctx_bucket)

    if not buckets:
        bucket = set()
        _urls.set(bucket)
        buckets.append(bucket)

    for bucket in buckets:
        if norm in bucket:
            return (
                f"同一轮已抓取过 {norm}，请勿重复调用 scrape；"
                "请根据上一轮工具结果直接总结。"
            )
    for bucket in buckets:
        bucket.add(norm)
    return None


__all__ = [
    "check_and_record_scrape",
    "is_firecrawl_scrape_tool",
    "normalize_scrape_url",
    "scrape_url_from_args",
    "turn_scrape_dedup_scope",
]

"""URL safety parse best-effort helpers (P0-A)."""

from __future__ import annotations

from urllib.parse import ParseResult, urlparse


def urlparse_safe(url: str) -> ParseResult | None:
    try:
        return urlparse(url.strip())
    except Exception:
        return None

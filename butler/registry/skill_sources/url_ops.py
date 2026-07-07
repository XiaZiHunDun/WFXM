"""URL skill fetch best-effort helpers (P0-A)."""

from __future__ import annotations

import logging

import httpx

from butler.registry.url_safety import is_safe_url

logger = logging.getLogger(__name__)


def fetch_url_skill_text_safe(url: str) -> str | None:
    try:
        resp = httpx.get(url, timeout=30.0, follow_redirects=False)
        if resp.status_code in (301, 302, 303, 307, 308):
            loc = resp.headers.get("location", "")
            if loc and is_safe_url(loc):
                resp = httpx.get(loc, timeout=30.0, follow_redirects=False)
        resp.raise_for_status()
        return str(resp.text)
    except Exception as exc:
        logger.debug("url fetch failed %s: %s", url, exc)
        return None

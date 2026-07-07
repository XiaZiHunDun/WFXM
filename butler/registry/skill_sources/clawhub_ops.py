"""ClawHub HTTP fetch best-effort helpers (P0-A)."""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


def clawhub_get_json_safe(url: str, *, params: dict[str, Any] | None = None) -> Any | None:
    try:
        resp = httpx.get(url, params=params or {}, timeout=25.0)
        if resp.status_code != 200:
            return None
        return resp.json()
    except Exception as exc:
        logger.debug("clawhub GET %s: %s", url, exc)
        return None


def fetch_inline_file_text_safe(url: str) -> str | None:
    try:
        resp = httpx.get(url, timeout=20.0)
        if resp.status_code == 200:
            return str(resp.text)
    except Exception as exc:
        logger.debug("extract inline files skipped: %s", exc)
    return None

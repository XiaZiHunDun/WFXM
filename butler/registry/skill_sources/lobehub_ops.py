"""LobeHub API fetch best-effort helpers (P0-A)."""

from __future__ import annotations

import logging
from typing import Any, cast

import httpx

logger = logging.getLogger(__name__)


def lobehub_search_api_json_safe(
    url: str,
    *,
    params: dict[str, Any],
    headers: dict[str, str],
) -> dict[str, Any] | None:
    try:
        resp = httpx.get(
            url,
            params=params,
            headers=headers,
            timeout=25.0,
        )
        if resp.status_code != 200:
            logger.debug("lobehub search HTTP %s", resp.status_code)
            return None
        data = resp.json()
        return data if isinstance(data, dict) else None
    except Exception as exc:
        logger.debug("lobehub search: %s", exc)
        return None


def lobehub_download_bytes_safe(
    url: str,
    *,
    headers: dict[str, str],
) -> bytes | None:
    try:
        from butler.registry.url_safety import safe_registry_get

        resp = safe_registry_get(url, headers=headers, timeout=60.0)
        if resp.status_code != 200:
            return None
        return cast(bytes | None, resp.content)
    except Exception as exc:
        logger.debug("lobehub download %s: %s", url, exc)
        return None

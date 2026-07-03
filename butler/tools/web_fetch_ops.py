"""Web fetch HTTP helpers (P0-A)."""

from __future__ import annotations

import json

import httpx


def fetch_url_bytes_safe(
    target: str,
    *,
    timeout: float,
    max_bytes: int,
    headers: dict[str, str],
) -> tuple[bytes | None, str | None, str | None]:
    from butler.registry.url_safety import safe_http_get_bytes

    try:
        raw, ctype = safe_http_get_bytes(
            target,
            timeout=timeout,
            max_bytes=max_bytes,
            headers=headers,
        )
        return raw, ctype, None
    except httpx.HTTPStatusError as exc:
        code = exc.response.status_code if exc.response is not None else 0
        return None, None, json.dumps({"error": f"HTTP {code}", "url": target})
    except ValueError as exc:
        return None, None, json.dumps({"error": str(exc), "url": target})
    except httpx.HTTPError as exc:
        return None, None, json.dumps({"error": str(exc), "url": target})
    except Exception as exc:
        return None, None, json.dumps({"error": str(exc), "url": target})

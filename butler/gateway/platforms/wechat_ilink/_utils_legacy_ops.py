"""WeChat iLink legacy utils best-effort helpers (P0-A)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


def read_json_dict_safe(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def restore_context_tokens_from_file(
    path: Path,
    account_id: str,
    *,
    safe_id: Any,
) -> dict[str, str] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning(
            "wechat: failed to restore context tokens for %s: %s",
            safe_id(account_id),
            exc,
        )
        return None
    if not isinstance(data, dict):
        return None
    return {str(k): str(v) for k, v in data.items() if isinstance(v, str) and v}


def persist_context_tokens_loud(
    *,
    write_fn: Any,
    account_id: str,
    safe_id: Any,
) -> None:
    try:
        write_fn()
    except Exception as exc:
        logger.warning(
            "wechat: failed to persist context tokens for %s: %s",
            safe_id(account_id),
            exc,
        )


def parse_wechat_cdn_url_loud(url: str) -> tuple[str, str]:
    try:
        parsed = urlparse(url)
        return parsed.scheme.lower(), parsed.hostname or ""
    except Exception as exc:
        raise ValueError(f"Unparseable media URL: {url!r}") from exc


def load_sync_buf_field_safe(path: Path, *, field: str = "get_updates_buf") -> str:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return str(data.get(field) or "")
    except Exception:
        pass
    return ""

"""Remote compact HTTP best-effort helpers (P0-A)."""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any

from butler.core.best_effort import safe_best_effort

logger = logging.getLogger(__name__)


def post_remote_compact_request_safe(
    req: urllib.request.Request,
    *,
    timeout: int,
    url: str,
) -> dict[str, Any] | None:
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except urllib.error.HTTPError as exc:
        logger.info("Remote compact HTTP %s at %s", exc.code, url)
        return None
    except Exception as exc:
        logger.debug("Remote compact failed: %s", exc)
        return None


def record_remote_compact_recovery_safe() -> None:
    def _run() -> None:
        from butler.ops.retry_buckets import record_recovery_event

        record_recovery_event("remote_compact_ok")

    safe_best_effort(_run, label="remote_compact.recovery_event", default=None)

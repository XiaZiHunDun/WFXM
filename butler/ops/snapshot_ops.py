"""Ops snapshot collection best-effort helpers (P0-A)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def load_runtime_run_json_safe(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def list_active_failure_streaks_safe() -> list[dict[str, Any]]:
    try:
        from butler.runtime.failure_tracker import list_active_streaks

        streaks = list_active_streaks()
        return streaks if isinstance(streaks, list) else []
    except Exception as exc:
        logger.debug("collect ops snapshot skipped: %s", exc)
        return []

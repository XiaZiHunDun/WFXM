"""Dev metrics load best-effort helpers (P0-A)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, cast

logger = logging.getLogger(__name__)


def parse_metrics_completed_tasks(data: dict[str, Any]) -> list[dict[str, Any]]:
    rows = data.get("completed_tasks", [])
    return rows if isinstance(rows, list) else []


def load_metrics_json_safe(path: Path) -> dict[str, Any] | None:
    try:
        return cast(dict[str, Any] | None, json.loads(path.read_text(encoding="utf-8")))
    except Exception as exc:
        logger.warning("Failed to load metrics: %s", exc)
        return None

"""Memory metrics load best-effort helpers (P0-A)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def load_metrics_sessions_from_file_safe(path: Path) -> dict[str, dict[str, Any]] | None:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        sessions = data.get("sessions") if isinstance(data, dict) else None
        if not isinstance(sessions, dict):
            return {}
        out: dict[str, dict[str, Any]] = {}
        for sid, sdata in sessions.items():
            if isinstance(sdata, dict):
                out[str(sid)] = sdata
        return out
    except Exception as exc:
        logger.warning("Failed to load memory metrics: %s", exc)
        return None

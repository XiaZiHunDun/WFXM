"""Terminal pattern approval persistence best-effort helpers (P0-A)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from butler.core.best_effort import safe_best_effort

logger = logging.getLogger(__name__)


def load_pattern_approval_map_safe(path: Path) -> dict[str, Any] | None:
    """Return approval map, or ``None`` when read/parse failed."""

    def _run() -> dict[str, Any]:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("pattern approval map is not a dict")
        return data

    result = safe_best_effort(
        _run,
        label="terminal_pattern_approval.load",
        default=None,
    )
    return result if isinstance(result, dict) else None


def load_pattern_approval_map_for_write_safe(path: Path) -> dict[str, Any]:
    result = load_pattern_approval_map_safe(path)
    return dict(result) if isinstance(result, dict) else {}

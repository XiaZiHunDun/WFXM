"""Media telemetry JSON state best-effort helpers (P0-A)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from butler.core.best_effort import safe_best_effort


def load_json_dict_safe(path: Path) -> dict[str, Any]:
    def _run() -> dict[str, Any]:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("telemetry state is not a dict")
        return raw

    result = safe_best_effort(
        _run,
        label="media_telemetry.load_json",
        default={},
    )
    return result if isinstance(result, dict) else {}

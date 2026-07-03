"""B9 promote queue read best-effort helpers (P0-A)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from butler.core.best_effort import safe_best_effort


def read_promotion_queue_records_safe(path: Path) -> list[dict[str, Any]]:
    def _run() -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            rec = json.loads(line)
            if isinstance(rec, dict):
                rows.append(rec)
        return rows

    result = safe_best_effort(
        _run,
        label="delegate_failure_b9_promote.queue_read",
        default=[],
    )
    return list(result) if isinstance(result, list) else []

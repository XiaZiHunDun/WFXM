"""Two-week gate before SWE-bench Lite full LIVE (15 instances)."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

_SNAPSHOTS_NAME = "swe_weekly_snapshots.jsonl"
_DEFAULT_MIN_WEEKS = 2
_DEFAULT_MIN_PASS_RATE = 1.0


def snapshots_path() -> Path:
    from butler.config import get_butler_home

    return get_butler_home() / "audit" / _SNAPSHOTS_NAME


def record_swe_weekly_snapshot(
    *,
    week: int,
    passed: int,
    total: int,
    mode: str = "live",
    instance_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Append weekly SWE subset result (idempotent per ISO week)."""
    path = snapshots_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    pass_rate = round(passed / total, 4) if total else 0.0
    rows: list[dict[str, Any]] = []
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    # Replace same-week row so re-runs within a week update rather than duplicate.
    rows = [r for r in rows if int(r.get("week") or 0) != week]
    row = {
        "week": week,
        "passed": passed,
        "total": total,
        "pass_rate": pass_rate,
        "mode": mode,
        "instance_ids": list(instance_ids or []),
        "recorded_at": time.time(),
    }
    rows.append(row)
    rows.sort(key=lambda r: int(r.get("week") or 0))
    path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )
    return row


def evaluate_swe_full_entry_gate(
    *,
    min_consecutive_weeks: int = _DEFAULT_MIN_WEEKS,
    min_pass_rate: float = _DEFAULT_MIN_PASS_RATE,
) -> dict[str, Any]:
    """Return whether full SWE-bench Lite LIVE is allowed."""
    path = snapshots_path()
    if not path.is_file():
        return {
            "allowed": False,
            "reason": "no_snapshots",
            "min_consecutive_weeks": min_consecutive_weeks,
            "min_pass_rate": min_pass_rate,
            "recent_weeks": [],
        }
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    rows.sort(key=lambda r: int(r.get("week") or 0), reverse=True)
    qualifying: list[dict[str, Any]] = []
    for row in rows:
        if str(row.get("mode") or "live") != "live":
            continue
        if float(row.get("pass_rate") or 0) < min_pass_rate:
            break
        if int(row.get("total") or 0) <= 0:
            break
        qualifying.append(row)
        if len(qualifying) >= min_consecutive_weeks:
            break
    allowed = len(qualifying) >= min_consecutive_weeks
    reason = "ok" if allowed else "need_more_weekly_passes"
    if not rows:
        reason = "no_snapshots"
    elif qualifying and len(qualifying) < min_consecutive_weeks:
        reason = f"only_{len(qualifying)}_qualifying_week"
    return {
        "allowed": allowed,
        "reason": reason,
        "min_consecutive_weeks": min_consecutive_weeks,
        "min_pass_rate": min_pass_rate,
        "qualifying_weeks": [int(r.get("week") or 0) for r in qualifying],
        "recent_weeks": rows[:5],
        "snapshots_path": str(path),
    }


__all__ = [
    "evaluate_swe_full_entry_gate",
    "record_swe_weekly_snapshot",
    "snapshots_path",
]

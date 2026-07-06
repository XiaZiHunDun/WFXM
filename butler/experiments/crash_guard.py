"""Consecutive experiment crash detection (autoresearch fast-fail subset)."""

from __future__ import annotations

import os
from pathlib import Path

from butler.experiments.ledger import _read_rows, experiments_ledger_path


def crash_block_threshold() -> int:
    try:
        from butler.env_parse import int_env

        return int(int_env("BUTLER_EXPERIMENT_CRASH_BLOCK", 3, min=1))
    except ValueError:
        return 3


def consecutive_crash_count(
    workspace: Path,
    *,
    hypothesis: str = "",
    job_id: str = "",
) -> int:
    """Count trailing ``crash`` rows matching *hypothesis* or *job_id* (newest last)."""
    rows = _read_rows(experiments_ledger_path(workspace))
    if not rows:
        return 0
    hyp = str(hypothesis or "").strip()
    jid = str(job_id or "").strip()
    streak = 0
    for row in reversed(rows):
        if str(row.get("status") or "").lower() != "crash":
            break
        if hyp and str(row.get("hypothesis") or "").strip() != hyp:
            break
        if jid and str(row.get("job_id") or "").strip() != jid:
            break
        streak += 1
    return streak


def should_block_experiment_run(
    workspace: Path,
    *,
    hypothesis: str = "",
    job_id: str = "",
) -> tuple[bool, str]:
    """Return (blocked, reason) when crash streak reaches threshold."""
    n = consecutive_crash_count(workspace, hypothesis=hypothesis, job_id=job_id)
    threshold = crash_block_threshold()
    if n < threshold:
        return False, ""
    label = hypothesis or job_id or "recent"
    return (
        True,
        f"实验连续 crash {n} 次（阈值 {threshold}），建议先修 harness 或改假设: {label[:60]}",
    )


__all__ = [
    "consecutive_crash_count",
    "crash_block_threshold",
    "should_block_experiment_run",
]

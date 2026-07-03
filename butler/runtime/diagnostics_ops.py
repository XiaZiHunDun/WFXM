"""Runtime diagnostics best-effort helpers (P0-A)."""

from __future__ import annotations

from pathlib import Path

from butler.core.best_effort import safe_best_effort


def count_runtime_push_queue_pending_safe(qpath: Path) -> int:
    def _run() -> int:
        if not qpath.is_file():
            return 0
        return sum(1 for ln in qpath.read_text(encoding="utf-8").splitlines() if ln.strip())

    result = safe_best_effort(
        _run,
        label="runtime_diagnostics.push_queue",
        default=0,
    )
    return int(result) if isinstance(result, int) else 0


def format_failure_streak_lines_safe() -> list[str]:
    def _run() -> list[str]:
        from butler.runtime.failure_tracker import format_failure_streak_lines

        return list(format_failure_streak_lines())

    result = safe_best_effort(
        _run,
        label="runtime_diagnostics.failure_streaks",
        default=[],
    )
    return list(result) if isinstance(result, list) else []

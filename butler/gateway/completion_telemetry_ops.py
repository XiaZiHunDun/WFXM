"""Completion telemetry best-effort helpers (P0-A)."""

from __future__ import annotations

from butler.core.best_effort import safe_best_effort


def push_queue_pending_count_safe(*, chat_id: str = "") -> int:
    def _run() -> int:
        from butler.runtime.push_queue import count_pending_pushes

        return int(count_pending_pushes(chat_id=chat_id or None))

    result = safe_best_effort(
        _run,
        label="completion_telemetry.push_queue_pending",
        default=0,
    )
    return int(result or 0)

"""Session read recall gate best-effort helpers (P0-A)."""

from __future__ import annotations

from butler.core.best_effort import safe_best_effort


def session_read_recall_gate_active_safe() -> bool:
    def _run() -> bool:
        from butler.execution_context import is_session_read_recall_gate_active

        return bool(is_session_read_recall_gate_active())

    result = safe_best_effort(
        _run,
        label="session_recall_intent.gate_active",
        default=False,
    )
    return bool(result)

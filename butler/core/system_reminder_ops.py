"""System reminder build best-effort helpers (P0-A)."""

from __future__ import annotations

from butler.core.best_effort import safe_best_effort


def build_dynamic_system_reminder_safe() -> str | None:
    def _run() -> str:
        from butler.execution_context import get_current_orchestrator

        orch = get_current_orchestrator()
        if orch is None:
            raise ValueError("no orchestrator in context")
        reminder = orch.build_dynamic_system_reminder()
        text = str(reminder or "").strip()
        if not text:
            raise ValueError("empty dynamic reminder")
        return text

    result = safe_best_effort(_run, label="system_reminder.build", default=None)
    text = str(result or "").strip()
    return text or None

"""Permission command telemetry best-effort helpers (P0-A)."""

from __future__ import annotations

from butler.core.best_effort import safe_best_effort


def inc_terminal_sandbox_escalation_approved_safe(session_key: str) -> None:
    def _run() -> None:
        from butler.ops.runtime_metrics import inc

        inc("terminal_sandbox_escalation_approved", session_key=session_key)

    safe_best_effort(
        _run,
        label="permission_commands.sandbox_escalation_metric",
        default=None,
    )

"""Delegate record best-effort helpers (P0-A)."""

from __future__ import annotations

from typing import Any

from butler.core.best_effort import safe_best_effort


def run_subagent_start_hooks_safe(state: Any) -> str | None:
    def _run() -> str:
        from butler.hooks.runner import run_subagent_start_hooks

        subagent_ctx = run_subagent_start_hooks(
            agent_type=state.role,
            agent_id=state.task_id or f"delegate-{state.role}",
            task_preview=state.task,
            task_id=state.task_id,
            session_key=state.session_key,
        )
        if not subagent_ctx:
            raise ValueError("empty subagent hook context")
        return "\n\n".join(subagent_ctx) + "\n\n" + state.user_msg

    result = safe_best_effort(
        _run,
        label="delegate_record.subagent_hooks",
        default=None,
    )
    return str(result) if isinstance(result, str) else None

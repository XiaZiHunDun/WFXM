"""Delegate run best-effort helpers (P0-A)."""

from __future__ import annotations

from typing import Any

from butler.core.best_effort import safe_best_effort


def delegate_langfuse_callbacks_safe(state: Any) -> Any | None:
    def _run() -> Any:
        from butler.ops.langfuse_tracer import delegate_run_callbacks

        return delegate_run_callbacks(
            parent_session_key=state.session_key,
            child_session_key=state.child_session_key or state.session_key,
            role=state.role,
            task=state.task,
            task_id=state.task_id,
        )

    return safe_best_effort(
        _run,
        label="delegate_run.langfuse_callbacks",
        default=None,
    )


def unregister_delegate_loop_safe(session_key: str, agent: Any) -> None:
    def _run() -> None:
        from butler.runtime.delegate_registry import unregister_delegate_loop

        unregister_delegate_loop(session_key, agent)

    safe_best_effort(_run, label="delegate_run.unregister_loop", default=None)

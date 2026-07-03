"""Implicit tool context best-effort helpers (P0-A)."""

from __future__ import annotations

from pathlib import Path

from butler.core.best_effort import safe_best_effort


def resolve_project_workspace_safe() -> Path | None:
    def _run() -> Path:
        from butler.execution_context import get_current_orchestrator, get_current_session_key

        orch = get_current_orchestrator()
        if orch is None:
            raise ValueError("orchestrator unavailable")
        pm = getattr(orch, "project_manager", None)
        if pm is None:
            raise ValueError("project manager unavailable")
        proj = pm.get_current(session_key=str(get_current_session_key() or ""))
        if proj is None:
            raise ValueError("no current project")
        return Path(proj.workspace).expanduser().resolve()

    result = safe_best_effort(
        _run,
        label="tool_implicit_context.workspace",
        default=None,
    )
    return result if isinstance(result, Path) else None


def current_session_key_safe() -> str:
    def _run() -> str:
        from butler.execution_context import get_current_session_key

        return str(get_current_session_key() or "").strip()

    result = safe_best_effort(
        _run,
        label="tool_implicit_context.session_key",
        default="",
    )
    return str(result or "")


def current_workflow_step_safe() -> str:
    def _run() -> str:
        from butler.execution_context import get_current_workflow_step

        return str(get_current_workflow_step() or "").strip()

    result = safe_best_effort(
        _run,
        label="tool_implicit_context.workflow_step",
        default="",
    )
    return str(result or "")

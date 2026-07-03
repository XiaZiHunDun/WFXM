"""DESIGN.md context resolution best-effort helpers (P0-A)."""

from __future__ import annotations

from pathlib import Path

from butler.core.best_effort import safe_best_effort


def resolve_active_project_workspace_safe() -> Path | None:
    def _run() -> Path:
        from butler.execution_context import get_current_orchestrator, get_current_session_key

        orch = get_current_orchestrator()
        if orch is None:
            raise ValueError("no orchestrator")
        pm = getattr(orch, "project_manager", None)
        if pm is None:
            raise ValueError("no project manager")
        proj = pm.get_current(session_key=str(get_current_session_key() or ""))
        if proj is None:
            raise ValueError("no active project")
        return Path(proj.workspace)

    result = safe_best_effort(
        _run,
        label="design_md_sections.workspace",
        default=None,
    )
    return result if isinstance(result, Path) else None


def current_design_preset_safe() -> str:
    def _run() -> str:
        from butler.execution_context import get_current_orchestrator, get_current_session_key

        orch = get_current_orchestrator()
        if orch is None:
            return ""
        pm = getattr(orch, "project_manager", None)
        if pm is None:
            return ""
        proj = pm.get_current(session_key=str(get_current_session_key() or ""))
        if proj is None:
            return ""
        return str(getattr(proj, "design_preset", "") or "").strip()

    result = safe_best_effort(
        _run,
        label="design_md_sections.design_preset",
        default="",
    )
    return str(result or "").strip()

"""Project todos workspace resolution best-effort helpers (P0-A)."""

from __future__ import annotations

from pathlib import Path

from butler.core.best_effort import safe_best_effort


def get_active_project_workspace_safe() -> Path | None:
    def _run() -> Path:
        from butler.execution_context import get_current_orchestrator, get_current_session_key

        orch = get_current_orchestrator()
        sk = str(get_current_session_key() or "").strip()
        proj = orch.project_manager.get_current(session_key=sk)
        if proj is None or not getattr(proj, "workspace", None):
            raise ValueError("no active project workspace")
        return Path(proj.workspace)

    result = safe_best_effort(
        _run,
        label="project_todos.workspace",
        default=None,
    )
    return result if isinstance(result, Path) else None

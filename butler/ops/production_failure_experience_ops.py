"""Production failure experience best-effort helpers (P0-A)."""

from __future__ import annotations

from pathlib import Path

from butler.core.best_effort import safe_best_effort


def resolve_project_workspace_safe(project_name: str) -> Path | None:
    def _run() -> Path:
        from butler.project.manager import get_project_manager

        proj = get_project_manager().get_project(project_name)
        if proj is None or not getattr(proj, "workspace", None):
            raise ValueError("project workspace missing")
        return Path(proj.workspace).expanduser().resolve()

    result = safe_best_effort(
        _run,
        label="production_failure_experience.workspace",
        default=None,
    )
    return result if isinstance(result, Path) else None


def infer_b9_task_id_safe(task: str) -> str:
    def _run() -> str:
        from butler.dev_engine.prod_delegate_bridge import infer_b9_task_id

        return str(infer_b9_task_id(task) or "").strip()

    result = safe_best_effort(
        _run,
        label="production_failure_experience.infer_b9_task",
        default="",
    )
    return str(result or "").strip()

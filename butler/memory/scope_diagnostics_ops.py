"""Memory scope diagnostics best-effort helpers (P0-A)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from butler.core.best_effort import safe_best_effort


def resolve_project_workspace_safe(project_name: str) -> Path | None:
    pname = str(project_name or "").strip()
    if not pname:
        return None

    def _run() -> Path:
        from butler.project.manager import get_project_manager

        proj = get_project_manager().get_project(pname)
        if proj is None or not getattr(proj, "workspace", None):
            raise ValueError("project not found")
        return Path(proj.workspace).expanduser().resolve()

    result = safe_best_effort(
        _run,
        label="scope_diagnostics.project_workspace",
        default=None,
    )
    return result if isinstance(result, Path) else None


def stack_tags_for_project_safe(project_name: str) -> frozenset[str]:
    def _run() -> frozenset[str]:
        from butler.memory.memory_scope import stack_tags_for_project
        from butler.project.manager import get_project_manager

        proj = get_project_manager().get_project(project_name.strip())
        if proj is None:
            raise ValueError("project not found")
        return frozenset(stack_tags_for_project(proj))

    result = safe_best_effort(
        _run,
        label="scope_diagnostics.stack_tags",
        default=frozenset(),
    )
    return result if isinstance(result, frozenset) else frozenset()


def list_projects_l3_overview_safe() -> list[dict[str, Any]]:
    def _run() -> list[dict[str, Any]]:
        from butler.memory.memory_scope import project_coding_experiences_path
        from butler.project.manager import get_project_manager

        overview: list[dict[str, Any]] = []
        for proj in get_project_manager().list_projects():
            pws = Path(proj.workspace).expanduser().resolve()
            l3p = project_coding_experiences_path(pws)
            if not l3p.is_file():
                continue
            try:
                import json

                data = json.loads(l3p.read_text(encoding="utf-8"))
                recs = data if isinstance(data, list) else []
            except (json.JSONDecodeError, OSError):
                recs = []
            if not recs:
                continue
            overview.append(
                {
                    "project": proj.name,
                    "l3_total": len(recs),
                    "l3_path": str(l3p),
                }
            )
        return overview

    result = safe_best_effort(
        _run,
        label="scope_diagnostics.projects_overview",
        default=[],
    )
    return list(result) if isinstance(result, list) else []

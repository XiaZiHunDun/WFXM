"""MCP config merge best-effort helpers (P0-A)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from butler.core.best_effort import safe_best_effort


def load_servers_yaml_block_safe(
    path: Path,
    *,
    record_corruption: Any,
) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:
        record_corruption(path, exc)
        return {}
    if not isinstance(data, dict):
        record_corruption(
            path,
            ValueError(f"mcp.yaml root is {type(data).__name__}, expected mapping"),
        )
        return {}
    block = data.get("servers")
    return block if isinstance(block, dict) else {}


def resolve_orchestrator_workspace_safe(session_key: str) -> Path | None:
    def _run() -> Path:
        from butler.execution_context import get_current_orchestrator, get_current_session_key

        sk = str(session_key or "").strip()
        orch = get_current_orchestrator()
        if orch is None or not hasattr(orch, "project_manager"):
            raise ValueError("orchestrator unavailable")
        if not sk:
            sk = str(get_current_session_key() or "").strip()
        proj = orch.project_manager.get_current(session_key=sk or None)
        if proj is None:
            raise ValueError("no current project")
        ws = getattr(proj, "workspace", None) or getattr(proj, "path", None)
        if not ws:
            raise ValueError("project workspace missing")
        p = Path(str(ws)).expanduser()
        if not p.is_dir():
            raise ValueError("workspace not a directory")
        return p.resolve()

    result = safe_best_effort(
        _run,
        label="mcp_merge.orchestrator_workspace",
        default=None,
    )
    return result if isinstance(result, Path) else None


def resolve_project_manager_workspace_safe(session_key: str) -> Path | None:
    sk = str(session_key or "").strip()
    if not sk:
        return None

    def _run() -> Path:
        from butler.config import load_settings
        from butler.project.manager import ProjectManager

        pm = ProjectManager(load_settings())
        proj = pm.get_current(session_key=sk)
        if proj is None:
            raise ValueError("no project for session")
        ws = getattr(proj, "workspace", None) or getattr(proj, "path", None)
        if not ws:
            raise ValueError("project workspace missing")
        p = Path(str(ws)).expanduser()
        if not p.is_dir():
            raise ValueError("workspace not a directory")
        return p.resolve()

    result = safe_best_effort(
        _run,
        label="mcp_merge.project_manager_workspace",
        default=None,
    )
    return result if isinstance(result, Path) else None

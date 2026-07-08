"""CLI helpers for owner + project MEMORY pending queues."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from butler.memory.pending_handlers import (
    format_pending_memory_list,
    handle_memory_pending_command,
)


def build_memory_orchestrator_stub(*, project: str = "", tenant: str = "default") -> Any:
    """Minimal orchestrator for pending handlers without a live gateway session."""
    from butler.config import get_butler_home
    from butler.memory.butler_memory import ButlerMemory
    from butler.memory.project_memory import ProjectMemory
    from butler.project.manager import get_project_manager

    bm = ButlerMemory(Path(get_butler_home()).expanduser().resolve(), tenant_id=tenant)
    pmgr = get_project_manager()
    proj_name = (project or "").strip()
    proj = pmgr.get_project(proj_name) if proj_name else pmgr.get_current()
    pmem = None
    if proj is not None and getattr(proj, "workspace", None):
        ws = Path(str(proj.workspace)).expanduser().resolve()
        if ws.is_dir():
            pmem = ProjectMemory(ws)

    class _PMgr:
        current_project = str(getattr(proj, "name", "") or "") if proj else None

        def get_current(self) -> Any:
            return proj

    class _Orch:
        butler_memory = bm
        _project_memory = pmem
        project_manager = _PMgr()

        def _reload_project_memory(self) -> None:
            nonlocal pmem, proj
            proj = pmgr.get_project(proj_name) if proj_name else pmgr.get_current()
            pmem = None
            if proj is not None and getattr(proj, "workspace", None):
                ws = Path(str(proj.workspace)).expanduser().resolve()
                if ws.is_dir():
                    pmem = ProjectMemory(ws)
            self._project_memory = pmem

    return _Orch()


def list_pending_text(*, project: str = "", tenant: str = "default") -> str:
    return format_pending_memory_list(
        build_memory_orchestrator_stub(project=project, tenant=tenant)
    )


def approve_pending_text(arg: str, *, project: str = "", tenant: str = "default") -> str:
    out = handle_memory_pending_command(
        build_memory_orchestrator_stub(project=project, tenant=tenant),
        "/批准记忆",
        arg,
    )
    return out or "批准失败（未知错误）"


def reject_pending_text(arg: str, *, project: str = "", tenant: str = "default") -> str:
    out = handle_memory_pending_command(
        build_memory_orchestrator_stub(project=project, tenant=tenant),
        "/拒绝记忆",
        arg,
    )
    return out or "拒绝失败（未知错误）"


__all__ = [
    "approve_pending_text",
    "build_memory_orchestrator_stub",
    "list_pending_text",
    "reject_pending_text",
]

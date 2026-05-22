"""Project Lead (厂长) gateway loop selection — phase 2."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from butler.project import Project

# Default pilot project(s); override with BUTLER_LEAD_PROJECTS=灵文1号,Other
_DEFAULT_LEAD_PROJECTS = frozenset({"灵文1号", "灵文1"})


def lead_project_names() -> frozenset[str]:
    raw = os.getenv("BUTLER_LEAD_PROJECTS", "").strip()
    if not raw:
        return _DEFAULT_LEAD_PROJECTS
    return frozenset(n.strip() for n in raw.split(",") if n.strip())


def _resolve_project(project_name: str) -> "Project | None":
    from butler.project_manager import get_project_manager

    pm = get_project_manager()
    name = (project_name or "").strip()
    if not name:
        return None
    proj = pm.get_project(name)
    if proj is not None:
        return proj
    matched = pm.resolve_project_name(name)
    if matched:
        return pm.get_project(matched)
    return None


def is_lead_project(project_name: str, *, project: "Project | None" = None) -> bool:
    """Lead if explicit ``lead: true``, env list, or ``pack: novel-factory`` (unless ``lead: false``)."""
    name = (project_name or "").strip()
    proj = project if project is not None else _resolve_project(name)

    if proj is not None and proj.lead is False:
        return False
    if proj is not None and proj.lead is True:
        return True
    if name and name in lead_project_names():
        return True
    if proj is not None and (proj.pack or "").strip() == "novel-factory":
        return True
    return False


def gateway_loop_role(project_name: str, *, project: "Project | None" = None) -> str:
    """Return AgentLoop role for gateway/CLI main thread: ``lead`` or ``butler``."""
    return "lead" if is_lead_project(project_name, project=project) else "butler"


def lead_mode_switch_suffix(project_name: str, *, project: "Project | None" = None) -> str:
    if not is_lead_project(project_name, project=project):
        return ""
    return (
        f"\n已进入【{project_name} · 厂长模式】（项目 Lead 对话引擎）。"
        "统筹与委派由本线程执行；改项目文件请说明交给 content/dev/review。"
        "读流水线请先查 novel-factory/workflow_state.json。"
    )


def lead_mode_banner_line() -> str:
    return "对话引擎: 项目 Lead（厂长）"

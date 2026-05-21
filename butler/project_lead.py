"""Project Lead (厂长) gateway loop selection — phase 2."""

from __future__ import annotations

import os

# Default pilot project(s); override with BUTLER_LEAD_PROJECTS=灵文1号,Other
_DEFAULT_LEAD_PROJECTS = frozenset({"灵文1号", "灵文1"})


def lead_project_names() -> frozenset[str]:
    raw = os.getenv("BUTLER_LEAD_PROJECTS", "").strip()
    if not raw:
        return _DEFAULT_LEAD_PROJECTS
    return frozenset(n.strip() for n in raw.split(",") if n.strip())


def is_lead_project(project_name: str) -> bool:
    return (project_name or "").strip() in lead_project_names()


def gateway_loop_role(project_name: str) -> str:
    """Return AgentLoop role for gateway/CLI main thread: ``lead`` or ``butler``."""
    return "lead" if is_lead_project(project_name) else "butler"


def lead_mode_switch_suffix(project_name: str) -> str:
    if not is_lead_project(project_name):
        return ""
    return (
        f"\n已进入【{project_name} · 厂长模式】（项目 Lead 对话引擎）。"
        "统筹与委派由本线程执行；改项目文件请说明交给 content/dev/review。"
        "读流水线请先查 novel-factory/workflow_state.json。"
    )


def lead_mode_banner_line() -> str:
    return "对话引擎: 项目 Lead（厂长）"

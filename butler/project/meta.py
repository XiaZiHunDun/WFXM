"""Project metadata helpers for diagnostics and Lead prompts."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from butler.project.model import Project


def lifecycle_label(project: "Project | None") -> str:
    if project is None:
        return ""
    lc = (getattr(project, "lifecycle", "") or "").strip()
    if lc:
        return lc
    st = (project.status or "").strip().lower()
    if st in ("complete", "completed", "archived"):
        return "complete"
    return "active"


def is_lead_enabled_for_project(project: "Project | None", project_name: str = "") -> bool:
    from butler.project.lead import is_lead_project

    name = (project_name or (project.name if project else "") or "").strip()
    return bool(is_lead_project(name, project=project))


def lifecycle_operating_hint(project: "Project | None") -> str:
    """Short block for Lead system prompt (维护态 vs 新书/活跃)."""
    if project is None:
        return ""
    lc = lifecycle_label(project)
    pack = (getattr(project, "pack", "") or "").strip()
    if lc == "complete":
        return (
            "## 运营态（维护态）\n"
            "本项目 `lifecycle` 为 **complete**：流水线已完结。主路径为读 "
            "`workflow_state.json`、runtime 只读巡检（`/运行`）、委派 dev 做检查；"
            "**不要**默认从零推进 STEP_1。若主公要**新开一本书/新选题**，"
            "先确认「新书立项」，再指引 init 脚本，勿自动跑完全厂 25 步。"
        )
    if pack == "novel-factory":
        return (
            "## 运营态（活跃创作）\n"
            "小说工厂能力包：推进前必读 state；改盘经委派；长流程走脚本或批准后的 runtime。"
        )
    if lc == "active":
        return "## 运营态（活跃）\n项目处于活跃开发与运营阶段。"
    return ""


def format_default_project_policy_lines(
    orchestrator: Any,
    session_key: str,
) -> list[str]:
    """C2: default project resolution policy for /诊断."""
    import os

    pm = orchestrator.project_manager
    default_env = os.getenv("BUTLER_DEFAULT_PROJECT", "").strip() or "(未设置)"
    session_proj = pm.resolve_active_project_name(session_key=session_key) or "(无)"
    lines = [
        "默认项目策略:",
        f"  BUTLER_DEFAULT_PROJECT: {default_env}",
        f"  本会话当前项目: {session_proj}",
    ]
    if default_env != "(未设置)" and session_proj == "(无)":
        lines.append("  解析: 新会话将使用环境默认项目")
    elif session_proj != "(无)":
        lines.append("  解析: 会话绑定优先于环境默认")
    lines.append("  切换: /切换 <项目名> · 新建: /项目 新建 <slug>")
    return lines


def format_project_meta_lines(
    project: "Project | None",
    *,
    project_name: str = "",
) -> list[str]:
    if project is None:
        return []
    name = project.name or project_name
    lines = [
        f"  项目类型: {project.type or '-'}",
    ]
    pack = (getattr(project, "pack", "") or "").strip()
    if pack:
        lines.append(f"  能力包 pack: {pack}")
    preset = (getattr(project, "design_preset", "") or "").strip()
    if preset:
        lines.append(f"  design_preset: {preset}")
    lc = lifecycle_label(project)
    if lc:
        lines.append(f"  运营态 lifecycle: {lc}")
    lead = is_lead_enabled_for_project(project, name)
    lines.append(f"  厂长 Lead: {'是' if lead else '否'}")
    jobs = project.workspace / "runtime" / "jobs.yaml"
    lines.append(f"  runtime jobs: {'有' if jobs.is_file() else '无'}")
    return lines


__all__ = [
    "format_project_meta_lines",
    "is_lead_enabled_for_project",
    "lifecycle_label",
    "lifecycle_operating_hint",
]

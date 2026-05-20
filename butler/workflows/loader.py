"""Load workflow definitions for the active Butler project."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from butler.workflows.schema import WorkflowDef, parse_workflow_data

if TYPE_CHECKING:
    from butler.project import Project

logger = logging.getLogger(__name__)

_BUILTIN_DIR = Path(__file__).resolve().parent / "builtin"


def _normalize_entry(entry: Any) -> dict[str, Any] | None:
    if isinstance(entry, dict):
        return dict(entry)
    if isinstance(entry, str) and entry.strip():
        return {"name": entry.strip()}
    return None


def load_builtin_workflow(name: str) -> WorkflowDef | None:
    key = str(name or "").strip()
    if not key:
        return None
    path = _BUILTIN_DIR / f"{key}.yaml"
    if not path.is_file():
        return None
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        logger.warning("Failed to load builtin workflow %s: %s", path, exc)
        return None
    if not isinstance(data, dict):
        return None
    data.setdefault("name", key)
    return parse_workflow_data(data, source="builtin")


def load_workspace_workflow(workspace: Path, name: str) -> WorkflowDef | None:
    key = str(name or "").strip()
    if not key:
        return None
    path = Path(workspace).expanduser().resolve() / ".butler" / "workflows" / f"{key}.yaml"
    if not path.is_file():
        return None
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        logger.warning("Failed to load workspace workflow %s: %s", path, exc)
        return None
    if not isinstance(data, dict):
        return None
    data.setdefault("name", key)
    return parse_workflow_data(data, source="workspace")


def resolve_workflow(project: "Project | None", name: str) -> WorkflowDef | None:
    """Merge project.yaml entry, workspace file, and builtin template."""
    key = str(name or "").strip()
    if not key or project is None:
        return load_builtin_workflow(key)

    base: WorkflowDef | None = None
    for entry in project.workflows or []:
        data = _normalize_entry(entry)
        if data and str(data.get("name") or "").strip() == key:
            base = parse_workflow_data(data, source="project")
            break

    if base is None:
        base = WorkflowDef(name=key, description="", steps=[], source="project")

    if not base.steps:
        ws = load_workspace_workflow(project.workspace, key)
        if ws is not None:
            base = ws
    if not base.steps:
        builtin = load_builtin_workflow(key)
        if builtin is not None:
            base = builtin
    elif not base.description:
        builtin = load_builtin_workflow(key)
        if builtin is not None and builtin.description:
            base.description = builtin.description

    return base if base.name else None


def list_workflows_for_project(project: "Project | None") -> list[WorkflowDef]:
    """List workflows declared on the project (resolved when possible)."""
    if project is None:
        return []
    seen: dict[str, WorkflowDef] = {}
    for entry in project.workflows or []:
        data = _normalize_entry(entry)
        if not data:
            continue
        stub = parse_workflow_data(data, source="project")
        if stub is None:
            continue
        resolved = resolve_workflow(project, stub.name)
        if resolved is not None:
            seen[resolved.name] = resolved
    return list(seen.values())


def format_workflows_for_prompt(project: "Project | None") -> str:
    workflows = list_workflows_for_project(project)
    if not workflows:
        return "(当前项目未配置工作流 — 可在 project.yaml 的 workflows 中声明，或使用内置模板名如 novel-factory)"
    lines: list[str] = []
    for wf in workflows:
        status = "可执行" if wf.runnable else "未定义步骤"
        lines.append(f"- **{wf.name}** ({status}): {wf.description or '无描述'}")
        if wf.runnable:
            step_bits = ", ".join(f"{s.id}({s.role})" for s in wf.steps)
            lines.append(f"  步骤: {step_bits}")
    lines.append("用户可用 `/工作流 run <名称> [补充说明]` 或工具 `run_workflow` 触发 DAG 执行。")
    return "\n".join(lines)


def format_workflows_for_wechat(project: "Project | None") -> str:
    """Plain-text workflow list (no Markdown) for WeChat delivery."""
    workflows = list_workflows_for_project(project)
    if not workflows:
        return (
            "当前项目未配置工作流。\n"
            "可在 project.yaml 的 workflows 中声明，或使用内置名 novel-factory。"
        )
    lines: list[str] = ["工作流列表："]
    for wf in workflows:
        status = "可执行" if wf.runnable else "未定义步骤"
        lines.append(f"1. {wf.name}（{status}）")
        if wf.description:
            lines.append(f"   {wf.description}")
        if wf.runnable:
            step_bits = " → ".join(f"{s.id}({s.role})" for s in wf.steps)
            lines.append(f"   步骤: {step_bits}")
    lines.append("运行: /工作流 run <名称> [补充说明]")
    return "\n".join(lines)


__all__ = [
    "format_workflows_for_prompt",
    "format_workflows_for_wechat",
    "list_workflows_for_project",
    "load_builtin_workflow",
    "load_workspace_workflow",
    "resolve_workflow",
]

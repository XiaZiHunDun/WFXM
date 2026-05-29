"""Load workflow definitions for the active Butler project."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from butler.workflows.schema import WorkflowDef, WorkflowStepDef, parse_workflow_data


def _step_summary(step: WorkflowStepDef) -> str:
    label = f"{step.id}({step.role})"
    if step.model is not None and not step.model.is_empty():
        label += f"[{step.model.provider or '-'}/{step.model.model or '-'}]"
    return label

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


def _merge_imported_steps(
    project: "Project | None",
    wf: WorkflowDef,
) -> WorkflowDef:
    if not wf.imports or project is None:
        return wf
    merged_steps: list[WorkflowStepDef] = []
    seen_ids: set[str] = set()
    for imp_name in wf.imports:
        imported = load_workspace_workflow(project.workspace, imp_name)
        if imported is None:
            imported = load_builtin_workflow(imp_name)
        if imported is None:
            continue
        for step in imported.steps:
            if step.id in seen_ids:
                continue
            merged_steps.append(step)
            seen_ids.add(step.id)
    for step in wf.steps:
        if step.id in seen_ids:
            continue
        merged_steps.append(step)
        seen_ids.add(step.id)
    wf.steps = merged_steps
    return wf


def resolve_workflow(project: "Project | None", name: str) -> WorkflowDef | None:
    """Merge project.yaml entry, workspace file, and builtin template."""
    key = str(name or "").strip()
    if not key or project is None:
        base = load_builtin_workflow(key)
        return base

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

    if base is not None:
        base = _merge_imported_steps(project, base)
    return base if base and base.name else None


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
            step_bits = ", ".join(_step_summary(s) for s in wf.steps)
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
            step_bits = " → ".join(_step_summary(s) for s in wf.steps)
            lines.append(f"   步骤: {step_bits}")
    lines.append("运行: /工作流 run <名称> [补充说明]")
    return "\n".join(lines)


def format_workflow_preview(project: "Project | None", name: str, *, dry_run: bool = False) -> str:
    """Show detailed step info, dependencies, and optionally validate without executing."""
    wf = resolve_workflow(project, name)
    if wf is None:
        return f"未找到工作流: {name}"

    lines = [f"工作流预览: {wf.name}"]
    if wf.description:
        lines.append(f"描述: {wf.description}")
    lines.append(f"状态: {'可执行' if wf.runnable else '未定义步骤'}")
    lines.append(f"步骤数: {len(wf.steps)}")
    lines.append("")

    errors: list[str] = []
    step_ids = {s.id for s in wf.steps}

    for i, step in enumerate(wf.steps, 1):
        gate = " [需确认]" if step.requires_approval else ""
        optional = " (可选)" if step.optional else ""
        lines.append(f"{i}. {step.id} — 角色: {step.role}{gate}{optional}")
        lines.append(f"   任务: {step.task[:120]}")
        if step.depends_on:
            deps = ", ".join(step.depends_on)
            lines.append(f"   依赖: {deps}")
            for dep in step.depends_on:
                if dep not in step_ids:
                    errors.append(f"步骤 {step.id} 依赖不存在的步骤 {dep}")
        if step.model and not step.model.is_empty():
            lines.append(f"   模型: {step.model.provider or '-'}/{step.model.model or '-'}")
        if step.tools:
            lines.append(f"   工具: {', '.join(step.tools)}")
        lines.append("")

    if dry_run:
        lines.append("--- dry-run 验证 ---")
        if errors:
            for err in errors:
                lines.append(f"  [错误] {err}")
        else:
            lines.append("  验证通过，所有依赖关系正确。")

    return "\n".join(lines)


__all__ = [
    "format_workflow_preview",
    "format_workflows_for_prompt",
    "format_workflows_for_wechat",
    "list_workflows_for_project",
    "load_builtin_workflow",
    "load_workspace_workflow",
    "resolve_workflow",
]

"""Shared slash-command handler for workflow list/run."""

from __future__ import annotations

from typing import Any

from butler.workflows.loader import format_workflows_for_prompt, list_workflows_for_project, resolve_workflow
from butler.workflows.runner import run_workflow_for_project


def handle_workflow_command(
    orchestrator: Any,
    arg: str,
    *,
    session_key: str = "",
    platform: str = "",
) -> str:
    """Parse ``/workflow`` / ``/工作流`` and return response text."""
    project = orchestrator.project_manager.get_current()
    current_name = orchestrator.project_manager.current_project or ""
    if project is None:
        return (
            "当前未选择项目，无法列出工作流。\n"
            "请先发送：/切换 灵文\n"
            "然后再发：/工作流 list"
        )

    parts = (arg or "").strip().split(maxsplit=1)
    sub = (parts[0].lower() if parts else "") or "list"
    hint = parts[1].strip() if len(parts) > 1 else ""

    if sub in {"list", "ls", "列表", ""}:
        from butler.workflows.loader import format_workflows_for_wechat

        if platform in ("wechat", "weixin", "微信"):
            header = f"项目: {current_name}\n" if current_name else ""
            return header + format_workflows_for_wechat(project)
        return format_workflows_for_prompt(project)

    if sub in {"run", "start", "执行", "运行"}:
        run_parts = hint.split(maxsplit=1)
        if not run_parts or not run_parts[0].strip():
            names = ", ".join(wf.name for wf in list_workflows_for_project(project)) or "(无)"
            return f"用法: /工作流 run <名称> [补充说明]\n可用: {names}"
        wf_name = run_parts[0].strip()
        user_hint = run_parts[1].strip() if len(run_parts) > 1 else ""
        wf = resolve_workflow(project, wf_name)
        if wf is None:
            return f"未找到工作流: {wf_name}"
        return run_workflow_for_project(
            project,
            wf_name,
            user_hint=user_hint,
            session_key=session_key,
            orchestrator=orchestrator,
        )

    # Shorthand: `/工作流 novel-factory 补充说明`
    wf = resolve_workflow(project, sub)
    if wf is None:
        return (
            f"未知子命令或工作流: {sub}\n"
            "用法: /工作流 list | /工作流 run <名称> [说明]"
        )
    return run_workflow_for_project(
        project,
        sub,
        user_hint=hint,
        session_key=session_key,
        orchestrator=orchestrator,
    )


__all__ = ["handle_workflow_command"]

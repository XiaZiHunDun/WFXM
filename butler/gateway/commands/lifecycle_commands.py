"""Session lifecycle and system management commands:
/doctor, /导出, /回滚, /分叉, /记忆提炼, /确认安装, /技能, /mcp, /config, /tasks, /workflow.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from butler.gateway.command_registry import CommandContext, CommandDef, register
from butler.gateway.owner_gate import is_gateway_owner, owner_required_message

logger = logging.getLogger(__name__)


def _require_owner(ctx: CommandContext) -> Optional[str]:
    """Sprint 12 SEC-12-2: 生命周期/系统管理类命令 owner 守门。"""
    if not is_gateway_owner(
        platform=ctx.platform, external_id=ctx.external_id, session_key=ctx.session_key
    ):
        return owner_required_message()
    return None


def _cmd_doctor(ctx: CommandContext) -> Optional[str]:
    gate = _require_owner(ctx)
    if gate:
        return gate
    from butler.ops.security_audit import format_audit_report, run_security_audit

    workspace = None
    try:
        proj = ctx.orchestrator.project_manager.get_current(session_key=ctx.session_key)
        if proj is not None:
            from pathlib import Path

            workspace = Path(proj.workspace)
    except Exception as exc:
        logger.debug("Security audit workspace resolve skipped: %s", exc)
    return format_audit_report(run_security_audit(workspace=workspace))


def _cmd_export(ctx: CommandContext) -> Optional[str]:
    gate = _require_owner(ctx)
    if gate:
        return gate
    from butler.gateway.export_commands import handle_export_session_command

    return handle_export_session_command(
        ctx.arg,
        platform=ctx.platform,
        external_id=ctx.external_id,
        session_key=ctx.session_key,
    )


def _cmd_revert(ctx: CommandContext) -> Optional[str]:
    from butler.gateway.owner_gate import is_gateway_owner, owner_required_message
    from butler.core.transcript_revert import truncate_transcript

    if not is_gateway_owner(
        platform=ctx.platform, external_id=ctx.external_id, session_key=ctx.session_key
    ):
        return owner_required_message()
    keep = 0
    if ctx.arg.strip().isdigit():
        keep = int(ctx.arg.strip())
    result = truncate_transcript(ctx.session_key, keep_last_lines=keep or None)
    if not result.get("ok"):
        return f"Transcript 回滚失败: {result.get('error', '?')}"
    if result.get("skipped"):
        return f"Transcript 无需回滚（当前 {result.get('lines_after', '?')} 行）"
    return (
        f"已截断 transcript：丢弃 {result.get('dropped_lines', 0)} 行，"
        f"保留约 {result.get('lines_after', 0)} 行（不含内存中的对话）。"
    )


def _cmd_fork(ctx: CommandContext) -> Optional[str]:
    from butler.gateway.owner_gate import is_gateway_owner, owner_required_message
    from butler.core.transcript_fork import fork_transcript_at_user_message

    if not is_gateway_owner(
        platform=ctx.platform, external_id=ctx.external_id, session_key=ctx.session_key
    ):
        return owner_required_message()
    user_idx = 1
    if ctx.arg.strip().isdigit():
        user_idx = max(1, int(ctx.arg.strip()))
    result = fork_transcript_at_user_message(
        ctx.session_key, keep_from_user_index=user_idx,
    )
    if not result.get("ok"):
        err = result.get("error", "?")
        if err == "user_index_not_found":
            return (
                f"Fork 失败：未找到第 {user_idx} 条 user 消息"
                f"（共 {result.get('user_messages_found', 0)} 条 user）。"
            )
        return f"Transcript fork 失败: {err}"
    if result.get("skipped"):
        return f"Transcript 已在第 {user_idx} 条 user 消息处，无需 fork。"
    return (
        f"已从第 {user_idx} 条 user 消息 fork transcript："
        f"丢弃 {result.get('dropped_lines', 0)} 行，保留约 {result.get('lines_after', 0)} 行。"
    )


def _cmd_transcript_memory(ctx: CommandContext) -> Optional[str]:
    from butler.gateway.owner_gate import is_gateway_owner, owner_required_message
    from butler.memory.transcript_memory_pipeline import (
        extract_memory_from_transcript,
        transcript_memory_enabled,
    )

    if not is_gateway_owner(
        platform=ctx.platform, external_id=ctx.external_id, session_key=ctx.session_key
    ):
        return owner_required_message()
    if not transcript_memory_enabled():
        return "Transcript 记忆提炼未启用。设置 BUTLER_TRANSCRIPT_MEMORY=1 后重试。"
    project = ctx.arg.strip() or os.getenv("BUTLER_DEFAULT_PROJECT", "") or ""
    result = extract_memory_from_transcript(ctx.session_key, project_name=project)
    if not result.get("ok"):
        return f"记忆提炼失败: {result.get('error', '?')}"
    if result.get("skipped"):
        return (
            f"跳过提炼：transcript 消息不足（{result.get('message_count', 0)} 条，需 ≥4）。"
        )
    updates = int(result.get("memory_updates") or 0)
    errs = result.get("errors") or []
    if errs:
        return f"提炼完成：写入 {updates} 条；警告: {'; '.join(errs[:2])}"
    return f"提炼完成：从 transcript 写入 {updates} 条记忆。"


def _cmd_confirm_install(ctx: CommandContext) -> Optional[str]:
    gate = _require_owner(ctx)
    if gate:
        return gate
    from butler.gateway.registry_commands import handle_confirm_install_command

    return handle_confirm_install_command(
        ctx.arg,
        platform=ctx.platform,
        external_id=ctx.external_id,
        session_key=ctx.session_key,
    )


def _cmd_registry(ctx: CommandContext) -> Optional[str]:
    gate = _require_owner(ctx)
    if gate:
        return gate
    from butler.gateway.registry_commands import handle_registry_command

    return handle_registry_command(
        ctx.cmd,
        ctx.arg,
        platform=ctx.platform,
        external_id=ctx.external_id,
        session_key=ctx.session_key,
    )


def _cmd_config(ctx: CommandContext) -> Optional[str]:
    from butler.config_service import config_set, format_config_get, format_config_list
    from butler.gateway.owner_gate import is_gateway_owner, owner_required_message

    if not ctx.arg:
        return format_config_list()
    parts = ctx.arg.split(maxsplit=1)
    sub = parts[0].lower()
    sub_arg = parts[1].strip() if len(parts) > 1 else ""
    if sub == "list":
        return format_config_list(sub_arg)
    if sub == "get" and sub_arg:
        return format_config_get(sub_arg)
    if sub == "set":
        if not is_gateway_owner(
            platform=ctx.platform, external_id=ctx.external_id, session_key=ctx.session_key
        ):
            return owner_required_message()
        kv = sub_arg.split(maxsplit=1)
        if len(kv) == 2:
            result = config_set(kv[0], kv[1])
            if result.needs_reset:
                ctx.reset_loop()
            return result.message
        return "用法: /config set <变量名> <值>"
    return format_config_get(ctx.arg)


def _cmd_tasks(ctx: CommandContext) -> Optional[str]:
    gate = _require_owner(ctx)
    if gate:
        return gate
    from butler.runtime.task_store import (
        count_running_tasks,
        list_recent_tasks,
        mark_stale_tasks,
        task_stale_minutes,
    )

    stale = mark_stale_tasks(ctx.session_key, auto_fail=False)
    rows = list_recent_tasks(ctx.session_key, limit=5)
    if not rows:
        return "暂无委派任务记录。"
    lines = [
        "最近委派任务:",
        f"  running: {count_running_tasks(ctx.session_key)} · stale 阈值: {task_stale_minutes()} 分钟",
    ]
    if stale:
        lines.append(f"  ⚠ 僵死任务 {len(stale)} 个（发 /诊断 查看详情）")
    for row in rows:
        status = row.get("status") or "?"
        ok = row.get("success")
        mark = "✓" if ok is True else ("✗" if ok is False else "…")
        if row.get("stale"):
            mark = "⏱"
        child_sk = str(row.get("child_session_key") or "").strip()
        child_hint = f" · {child_sk}" if child_sk else ""
        bg = " [后台]" if row.get("background") else ""
        stale_tag = " [stale]" if row.get("stale") else ""
        lines.append(
            f"  {mark} {row.get('task_id')} [{status}]{stale_tag}{bg}{child_hint} "
            f"{(row.get('task_preview') or '')[:60]}"
        )
    return "\n".join(lines)


def _cmd_workflow(ctx: CommandContext) -> Optional[str]:
    gate = _require_owner(ctx)
    if gate:
        return gate
    from butler.workflows.commands import handle_workflow_command

    return handle_workflow_command(
        ctx.orchestrator,
        ctx.arg,
        session_key=ctx.session_key,
        platform=ctx.platform,
    )


_LIFECYCLE_COMMANDS = [
    CommandDef("/doctor", (), "系统管理", "安全审计报告", handler=_cmd_doctor),
    CommandDef("/导出", ("/export", "/export-session", "/导出会话"), "系统管理", "导出会话为 Markdown", handler=_cmd_export),
    CommandDef("/回滚", ("/transcript-revert", "/revert-transcript"), "系统管理", "回滚 transcript", handler=_cmd_revert),
    CommandDef("/分叉", ("/fork-transcript", "/transcript-fork", "/fork"), "系统管理", "会话分叉", handler=_cmd_fork),
    CommandDef("/记忆提炼", ("/transcript-memory", "/extract-transcript-memory"), "记忆", "从 transcript 提炼记忆", handler=_cmd_transcript_memory),
    CommandDef("/确认安装", ("/confirm-install",), "权限安全", "确认 Skill/MCP 安装", handler=_cmd_confirm_install),
    CommandDef("/技能", ("/skills",), "系统管理", "Skill 搜索/安装/管理", handler=_cmd_registry),
    CommandDef("/mcp", (), "系统管理", "MCP 搜索/安装/管理", handler=_cmd_registry),
    CommandDef("/config", ("/配置",), "系统管理", "查看/修改系统配置", handler=_cmd_config),
    CommandDef("/任务", ("/tasks",), "系统管理", "查看委派任务列表", handler=_cmd_tasks),
    CommandDef("/工作流", ("/workflow",), "系统管理", "工作流管理", handler=_cmd_workflow),
]

for _cmd in _LIFECYCLE_COMMANDS:
    register(_cmd)

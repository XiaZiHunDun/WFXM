"""Stateless informational commands: /总览, /预设, /帮助, /待办, /备忘, /通讯录, /记账, /打卡, /项目待办."""

from __future__ import annotations

from typing import Optional

from butler.gateway.command_registry import (
    CommandContext,
    CommandDef,
    register,
    require_owner,
)


def _cmd_overview(ctx: CommandContext) -> Optional[str]:
    gate = require_owner(ctx)
    if gate:
        return gate
    from butler.gateway.handler_helpers import _build_project_overview

    return _build_project_overview(ctx.orchestrator, ctx.session_key)


def _cmd_presets(ctx: CommandContext) -> Optional[str]:
    """List provider presets.

    owner-gate-opt-out: 公共只读，无 owner 数据；列出 butler:// preset URL
    """
    from butler.provider_presets import format_presets_list

    return format_presets_list()


def _cmd_help(ctx: CommandContext) -> Optional[str]:
    """Show help text.

    owner-gate-opt-out: 公共只读，无 owner 数据；命令帮助对所有白名单用户开放
    """
    from butler.gateway.help_commands import format_help_text

    return format_help_text(ctx.arg)


def _cmd_todos(ctx: CommandContext) -> Optional[str]:
    gate = require_owner(ctx)
    if gate:
        return gate
    from butler.core.session_todos import format_session_todos_for_wechat

    return format_session_todos_for_wechat(ctx.session_key)


def _cmd_memo(ctx: CommandContext) -> Optional[str]:
    gate = require_owner(ctx)
    if gate:
        return gate
    from butler.tools.memo import format_memos_for_wechat

    return format_memos_for_wechat(ctx.arg)


def _cmd_contacts(ctx: CommandContext) -> Optional[str]:
    gate = require_owner(ctx)
    if gate:
        return gate
    from butler.tools.contacts import format_contacts_for_wechat

    return format_contacts_for_wechat(ctx.arg)


def _cmd_expense(ctx: CommandContext) -> Optional[str]:
    gate = require_owner(ctx)
    if gate:
        return gate
    from butler.tools.expense import format_expense_for_wechat

    return format_expense_for_wechat(ctx.arg)


def _cmd_habits(ctx: CommandContext) -> Optional[str]:
    gate = require_owner(ctx)
    if gate:
        return gate
    from butler.tools.habits import format_habits_for_wechat

    return format_habits_for_wechat(ctx.arg)


def _cmd_project_todos(ctx: CommandContext) -> Optional[str]:
    gate = require_owner(ctx)
    if gate:
        return gate
    from butler.tools.project_todos import format_project_todos_for_wechat

    proj = ctx.orchestrator.project_manager.active_project
    if proj and getattr(proj, "workspace", None):
        from pathlib import Path

        return format_project_todos_for_wechat(Path(proj.workspace))
    return "无活跃项目。"


def _cmd_memory_status(ctx: CommandContext) -> Optional[str]:
    gate = require_owner(ctx)
    if gate:
        return gate
    from butler.gateway.memory_commands import format_memory_status

    return format_memory_status(ctx.orchestrator, session_key=ctx.session_key)


def _cmd_detail(ctx: CommandContext) -> Optional[str]:
    gate = require_owner(ctx)
    if gate:
        return gate
    from butler.report import get_last_report, format_detail
    from butler.report.format import (
        format_child_session_detail,
        parse_child_arg,
        parse_detail_section,
    )

    # Sprint 28 P1-3.4: --child <child_sk> 优先于 report 路径.
    remaining, child_sk = parse_child_arg(ctx.arg)
    if child_sk:
        return format_child_session_detail(child_sk)

    report = get_last_report(ctx.session_key)
    if report:
        return format_detail(report, section=parse_detail_section(remaining))
    return "暂无可展示的详细报告。"


def _cmd_budget(ctx: CommandContext) -> Optional[str]:
    """Show or hint token budget.

    owner-gate-opt-out: 公共只读，无 owner 数据；只显示预算提示文本
    """
    from butler.core.turn_token_budget import parse_token_budget_text

    if ctx.arg:
        probe = parse_token_budget_text(f"/budget {ctx.arg}")
        if probe:
            return (
                f"已识别本轮 token 预算约 {probe:,}。"
                "请直接发送任务并在句末加 +500k，或写「本轮尽量做完」。"
            )
    return (
        "用法：在任务句末加 +500k / +2m，或发送「本轮尽量做完」。"
        "也可：/budget 500k（提示预算，与下一条任务一并发送）。"
    )


# Sprint 17 SEC-11 owner-gate completion: 从 inline 迁移过来的 3 个 handler 加 owner gate
# (底层 handle_*_command 已有 gate, 这里 wrapper 再加一次防止 registry 直接 dispatch
# 绕过 + 静态扫描器 owner-gate-scan 报 0 gaps).


def _cmd_sessions(ctx: CommandContext) -> Optional[str]:
    gate = require_owner(ctx)
    if gate:
        return gate
    from butler.gateway.sessions_commands import handle_sessions_command

    return handle_sessions_command(
        ctx.orchestrator,
        ctx.arg,
        platform=ctx.platform,
        external_id=ctx.external_id,
        session_key=ctx.session_key,
    )


def _cmd_outcome(ctx: CommandContext) -> Optional[str]:
    gate = require_owner(ctx)
    if gate:
        return gate
    from butler.gateway.outcome_commands import handle_outcome_command

    return handle_outcome_command(
        ctx.orchestrator,
        ctx.arg,
        platform=ctx.platform,
        external_id=ctx.external_id,
        session_key=ctx.session_key,
    )


def _cmd_health(ctx: CommandContext) -> Optional[str]:
    """Sprint 11 TST-10-5: 从 inline 迁移 — 等价于原 handler._format_health_summary。"""
    gate = require_owner(ctx)
    if gate:
        return gate
    from butler.ops.health_report import (
        HealthReportInput,
        build_health_report,
        collect_mem_stats_for_health,
    )
    from butler.gateway.handler_helpers import _tool_audit_summary

    session_key = ctx.session_key
    health = ctx.session_registry.get_health(session_key)
    return build_health_report(
        HealthReportInput(
            session_key=session_key,
            health=health,
            tool_summary=_tool_audit_summary(session_key),
            mem_stats=collect_mem_stats_for_health(
                ctx.orchestrator, session_key, health
            ),
            orchestrator=ctx.orchestrator,
        )
    )


_INFO_COMMANDS = [
    CommandDef("/总览", ("/overview",), "项目管理", "项目总览与概要", handler=_cmd_overview),
    CommandDef("/预设", (), "模型", "列出 butler:// 预设", handler=_cmd_presets),
    CommandDef("/帮助", ("/help",), "系统管理", "命令帮助", handler=_cmd_help),
    CommandDef("/待办", ("/todo",), "对话控制", "查看/管理会话待办", handler=_cmd_todos),
    CommandDef("/备忘", ("/memo",), "日常生活", "查看备忘录", handler=_cmd_memo),
    CommandDef("/通讯录", ("/contacts",), "日常生活", "查看通讯录", handler=_cmd_contacts),
    CommandDef("/记账", ("/expense",), "日常生活", "查看记账概览", handler=_cmd_expense),
    CommandDef("/打卡", ("/habits",), "日常生活", "查看习惯打卡", handler=_cmd_habits),
    CommandDef("/项目待办", ("/project-todos",), "项目管理", "项目级待办事项", handler=_cmd_project_todos),
    CommandDef("/记忆状态", ("/memory-status",), "记忆", "查看记忆系统状态", handler=_cmd_memory_status),
    CommandDef("/详细", ("/detail",), "对话控制", "查看详细报告", handler=_cmd_detail),
    CommandDef("/预算", ("/budget",), "系统管理", "设置本轮 token 预算", handler=_cmd_budget),
    # Sprint 11 TST-10-5: 从 inline 迁移过来的命令
    CommandDef("/会话", ("/sessions",), "对话控制", "查看/管理会话", handler=_cmd_sessions),
    CommandDef("/评价", ("/outcome",), "系统管理", "评估/评价当前结果", handler=_cmd_outcome),
    CommandDef("/诊断", ("/health",), "系统管理", "系统诊断", handler=_cmd_health),
]


for _cmd in _INFO_COMMANDS:
    register(_cmd)

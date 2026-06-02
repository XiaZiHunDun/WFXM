"""Stateless informational commands: /总览, /预设, /帮助, /待办, /备忘, /通讯录, /记账, /打卡, /项目待办."""

from __future__ import annotations

from typing import Optional

from butler.gateway.command_registry import CommandContext, CommandDef, register
from butler.gateway.owner_gate import is_gateway_owner, owner_required_message


def _require_owner(ctx: CommandContext) -> Optional[str]:
    """Sprint 11 SEC-11-5: 私人数据 handler 守门。"""
    if not is_gateway_owner(
        platform=ctx.platform, external_id=ctx.external_id, session_key=ctx.session_key
    ):
        return owner_required_message()
    return None


def _cmd_overview(ctx: CommandContext) -> Optional[str]:
    from butler.gateway.handler_helpers import _build_project_overview

    return _build_project_overview(ctx.orchestrator, ctx.session_key)


def _cmd_presets(ctx: CommandContext) -> Optional[str]:
    from butler.provider_presets import format_presets_list

    return format_presets_list()


def _cmd_help(ctx: CommandContext) -> Optional[str]:
    from butler.gateway.help_commands import format_help_text

    return format_help_text(ctx.arg)


def _cmd_todos(ctx: CommandContext) -> Optional[str]:
    from butler.core.session_todos import format_session_todos_for_wechat

    return format_session_todos_for_wechat(ctx.session_key)


def _cmd_memo(ctx: CommandContext) -> Optional[str]:
    gate = _require_owner(ctx)
    if gate:
        return gate
    from butler.tools.memo import format_memos_for_wechat

    return format_memos_for_wechat(ctx.arg)


def _cmd_contacts(ctx: CommandContext) -> Optional[str]:
    gate = _require_owner(ctx)
    if gate:
        return gate
    from butler.tools.contacts import format_contacts_for_wechat

    return format_contacts_for_wechat(ctx.arg)


def _cmd_expense(ctx: CommandContext) -> Optional[str]:
    gate = _require_owner(ctx)
    if gate:
        return gate
    from butler.tools.expense import format_expense_for_wechat

    return format_expense_for_wechat(ctx.arg)


def _cmd_habits(ctx: CommandContext) -> Optional[str]:
    gate = _require_owner(ctx)
    if gate:
        return gate
    from butler.tools.habits import format_habits_for_wechat

    return format_habits_for_wechat(ctx.arg)


def _cmd_project_todos(ctx: CommandContext) -> Optional[str]:
    from butler.tools.project_todos import format_project_todos_for_wechat

    proj = ctx.orchestrator.project_manager.active_project
    if proj and getattr(proj, "workspace", None):
        from pathlib import Path

        return format_project_todos_for_wechat(Path(proj.workspace))
    return "无活跃项目。"


def _cmd_memory_status(ctx: CommandContext) -> Optional[str]:
    from butler.gateway.memory_commands import format_memory_status

    return format_memory_status(ctx.orchestrator, session_key=ctx.session_key)


def _cmd_detail(ctx: CommandContext) -> Optional[str]:
    from butler.report import get_last_report, format_detail
    from butler.report.format import parse_detail_section

    report = get_last_report(ctx.session_key)
    if report:
        return format_detail(report, section=parse_detail_section(ctx.arg))
    return "暂无可展示的详细报告。"


def _cmd_budget(ctx: CommandContext) -> Optional[str]:
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
]

for _cmd in _INFO_COMMANDS:
    register(_cmd)

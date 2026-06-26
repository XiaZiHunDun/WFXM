"""Owner P4-B slash: /改 (usage) · /转交CC (handoff pack)."""

from __future__ import annotations

from typing import Optional

from butler.gateway.command_registry import CommandContext, CommandDef, register, require_owner


def _cmd_edit(ctx: CommandContext) -> Optional[str]:
    """Usage-only; non-empty args expand in locked_phases before the loop."""
    gate = require_owner(ctx)
    if gate:
        return gate
    from butler.gateway.owner_delegate_shortcuts import format_edit_command_usage

    arg = (ctx.arg or "").strip()
    if not arg:
        return format_edit_command_usage()
    # Expanded path should not reach here; fallback delegate phrase.
    from butler.gateway.owner_delegate_shortcuts import (
        build_dev_delegate_prompt,
        parse_edit_command_arg,
        resolve_project_context,
    )

    name, _ = resolve_project_context(ctx.orchestrator, ctx.session_key)
    path, goal = parse_edit_command_arg(arg)
    return build_dev_delegate_prompt(path, goal, project_name=name)


def _cmd_cc_handoff(ctx: CommandContext) -> Optional[str]:
    gate = require_owner(ctx)
    if gate:
        return gate
    from butler.gateway.owner_delegate_shortcuts import (
        build_cc_handoff_package,
        resolve_project_context,
    )

    scope = (ctx.arg or "").strip()
    if not scope:
        return (
            "用法：/转交CC <范围或任务摘要>\n"
            "例：/转交CC 重构 auth 模块并补测试\n"
            "将生成可复制 CC 任务包（范围 · 项目 · 工作区）。"
        )
    name, ws = resolve_project_context(ctx.orchestrator, ctx.session_key)
    if not name:
        return "请先 /切换 到目标项目，再发 /转交CC …"
    return build_cc_handoff_package(
        scope,
        project_name=name,
        workspace=ws,
        session_key=ctx.session_key,
    )


_OWNER_SHORTCUT_COMMANDS: list[CommandDef] = [
    CommandDef(
        "/改",
        ("/edit",),
        "开发工具",
        "结构化委派：/改 <路径> <目标>",
        handler=_cmd_edit,
    ),
    CommandDef(
        "/转交CC",
        ("/转交cc", "/handoff-cc"),
        "开发工具",
        "生成本机 CC 任务包",
        handler=_cmd_cc_handoff,
    ),
]


def register_owner_shortcut_commands() -> None:
    for cmd in _OWNER_SHORTCUT_COMMANDS:
        register(cmd)


register_owner_shortcut_commands()

__all__ = ["register_owner_shortcut_commands"]

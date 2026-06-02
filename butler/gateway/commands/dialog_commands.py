"""Dialog control commands: /steer, /queue, /确认, /取消, /循环, /停止循环, /plan, /执行."""

from __future__ import annotations

import logging
from typing import Optional

from butler.gateway.command_registry import CommandContext, CommandDef, register
from butler.gateway.owner_gate import is_gateway_owner, owner_required_message

logger = logging.getLogger(__name__)


def _require_owner(ctx: CommandContext) -> Optional[str]:
    """Sprint 12 SEC-12-2: 会话状态变更类命令 owner 守门。"""
    if not is_gateway_owner(
        platform=ctx.platform, external_id=ctx.external_id, session_key=ctx.session_key
    ):
        return owner_required_message()
    return None


def _cmd_steer(ctx: CommandContext) -> Optional[str]:
    gate = _require_owner(ctx)
    if gate:
        return gate
    from butler.core.steer import format_steer_gateway_reply, is_run_active, steer

    active = is_run_active(ctx.session_key)
    accepted = bool(active and steer(ctx.arg, session_key=ctx.session_key))
    return format_steer_gateway_reply(accepted=accepted, active=active)


def _cmd_queue(ctx: CommandContext) -> Optional[str]:
    gate = _require_owner(ctx)
    if gate:
        return gate
    from butler.gateway.queue_settings import apply_queue_command

    return apply_queue_command(ctx.session_key, ctx.arg)


def _cmd_approve(ctx: CommandContext) -> Optional[str]:
    gate = _require_owner(ctx)
    if gate:
        return gate
    from butler.human_gate import resolve_human_gate_message

    return resolve_human_gate_message(ctx.session_key, "确认") or "当前没有待确认的工作流步骤。"


def _cmd_cancel(ctx: CommandContext) -> Optional[str]:
    gate = _require_owner(ctx)
    if gate:
        return gate
    from butler.human_gate import resolve_human_gate_message

    return resolve_human_gate_message(ctx.session_key, "取消") or "当前没有待确认的工作流步骤。"


def _cmd_goal_loop(ctx: CommandContext) -> Optional[str]:
    gate = _require_owner(ctx)
    if gate:
        return gate
    from butler.core.goal_loop import start_goal_loop

    return start_goal_loop(ctx.session_key, ctx.arg)


def _cmd_stop_goal_loop(ctx: CommandContext) -> Optional[str]:
    gate = _require_owner(ctx)
    if gate:
        return gate
    from butler.core.goal_loop import stop_goal_loop

    return stop_goal_loop(ctx.session_key)


def _cmd_plan_mode(ctx: CommandContext) -> Optional[str]:
    gate = _require_owner(ctx)
    if gate:
        return gate
    from butler.plan.mode import format_plan_mode_status, set_plan_mode

    arg_l = (ctx.arg or "").strip().lower()
    if arg_l in ("off", "exit", "执行", "退出", "关闭"):
        from butler.plan.mode import clear_plan_mode

        clear_plan_mode(ctx.session_key)
        ctx.reset_loop()
        return "已退出规划模式，可以委派与写入。"
    set_plan_mode(ctx.session_key, True)
    ctx.reset_loop()
    return format_plan_mode_status(ctx.session_key)


def _cmd_exit_plan(ctx: CommandContext) -> Optional[str]:
    gate = _require_owner(ctx)
    if gate:
        return gate
    from butler.plan.mode import clear_plan_mode

    clear_plan_mode(ctx.session_key)
    ctx.reset_loop()
    return "已退出规划模式，可以委派与写入。"


_DIALOG_COMMANDS = [
    CommandDef("/steer", ("/指引",), "对话控制", "插入引导消息", handler=_cmd_steer),
    CommandDef("/queue", (), "对话控制", "入站队列模式", handler=_cmd_queue),
    CommandDef("/确认", ("/approve",), "规划模式", "确认 workflow 步骤", handler=_cmd_approve),
    CommandDef("/取消", ("/cancel",), "规划模式", "取消 workflow 步骤", handler=_cmd_cancel),
    CommandDef("/循环", ("/loop",), "对话控制", "启动目标循环模式", handler=_cmd_goal_loop),
    CommandDef("/停止循环", ("/stoploop",), "对话控制", "停止目标循环", handler=_cmd_stop_goal_loop),
    CommandDef("/计划", ("/plan", "/规划"), "规划模式", "进入规划模式", handler=_cmd_plan_mode),
    CommandDef("/执行", ("/exit-plan", "/退出规划"), "规划模式", "退出规划，开始执行", handler=_cmd_exit_plan),
]

for _cmd in _DIALOG_COMMANDS:
    register(_cmd)

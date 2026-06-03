"""Dialog control commands.

Two groups migrated in different sprints:

Sprint 16 TST-10-5 第七批 (this file, 3 added at bottom):
  - /切换     (/switch)               — switch active project
  - /模型     (/model)                — view/change current model
  - /新对话   (/new)                  — reset current session

Pre-existing (owner-gated, Sprint 12 SEC-12-2):
  - /steer    (/指引)                 — inject steering message
  - /queue                             — inbound queue mode
  - /确认     (/approve)              — confirm workflow step
  - /取消     (/cancel)               — cancel workflow step
  - /循环     (/loop)                 — start goal loop mode
  - /停止循环 (/stoploop)             — stop goal loop
  - /计划     (/plan, /规划)          — enter plan mode
  - /执行     (/exit-plan, /退出规划)   — exit plan mode
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Optional

from butler.gateway.command_registry import (
    CommandContext,
    CommandDef,
    register,
    require_owner,
)

if TYPE_CHECKING:
    from butler.orchestrator import ButlerOrchestrator

logger = logging.getLogger(__name__)


def _cmd_steer(ctx: CommandContext) -> Optional[str]:
    gate = require_owner(ctx)
    if gate:
        return gate
    from butler.core.steer import format_steer_gateway_reply, is_run_active, steer

    active = is_run_active(ctx.session_key)
    accepted = bool(active and steer(ctx.arg, session_key=ctx.session_key))
    return format_steer_gateway_reply(accepted=accepted, active=active)


def _cmd_queue(ctx: CommandContext) -> Optional[str]:
    gate = require_owner(ctx)
    if gate:
        return gate
    from butler.gateway.queue_settings import apply_queue_command

    return apply_queue_command(ctx.session_key, ctx.arg)


def _cmd_approve(ctx: CommandContext) -> Optional[str]:
    gate = require_owner(ctx)
    if gate:
        return gate
    from butler.human_gate import resolve_human_gate_message

    return resolve_human_gate_message(ctx.session_key, "确认") or "当前没有待确认的工作流步骤。"


def _cmd_cancel(ctx: CommandContext) -> Optional[str]:
    gate = require_owner(ctx)
    if gate:
        return gate
    from butler.human_gate import resolve_human_gate_message

    return resolve_human_gate_message(ctx.session_key, "取消") or "当前没有待确认的工作流步骤。"


def _cmd_goal_loop(ctx: CommandContext) -> Optional[str]:
    gate = require_owner(ctx)
    if gate:
        return gate
    from butler.core.goal_loop import start_goal_loop

    return start_goal_loop(ctx.session_key, ctx.arg)


def _cmd_stop_goal_loop(ctx: CommandContext) -> Optional[str]:
    gate = require_owner(ctx)
    if gate:
        return gate
    from butler.core.goal_loop import stop_goal_loop

    return stop_goal_loop(ctx.session_key)


def _cmd_plan_mode(ctx: CommandContext) -> Optional[str]:
    gate = require_owner(ctx)
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
    gate = require_owner(ctx)
    if gate:
        return gate
    from butler.plan.mode import clear_plan_mode

    clear_plan_mode(ctx.session_key)
    ctx.reset_loop()
    return "已退出规划模式，可以委派与写入。"


# ── Sprint 16 TST-10-5 第七批: 项目切换 / 模型 / 新对话 (无 owner gate) ──


def format_switch_project_reply(
    orchestrator: "ButlerOrchestrator",
    session_registry: Any,
    session_key: str,
    arg: str,
    platform: str,
) -> str:
    """/切换 <项目名称>: 切换 chat 的活跃项目, 副作用: 重建 session."""
    if not arg:
        return "用法: /switch <项目名称>"
    parts = session_key.split(":", 2)
    plat = parts[0] if parts else platform
    cid = parts[1] if len(parts) > 1 else "default"
    pm = orchestrator.project_manager
    ok = pm.switch_project_for_chat(platform=plat, chat_id=cid, name=arg)
    if ok:
        new_name = pm.get_project_name_for_chat(platform=plat, chat_id=cid)
        cleared = session_registry.reset_sessions_for_chat(
            platform=plat,
            chat_id=cid,
        )
        extra = ""
        if cleared:
            extra = f"\n已重建对话引擎（清理 {len(cleared)} 个旧项目会话）。"
        from butler.project.lead import lead_mode_switch_suffix

        lead_note = lead_mode_switch_suffix(new_name)
        return (
            f"已切换到项目: {new_name}\n"
            "（下一条消息起使用新项目工具与 workspace。）"
            f"{extra}{lead_note}"
        )
    available = pm.list_projects()
    if available:
        names = [p.name for p in available]
        return (
            f"未找到项目: {arg}\n\n"
            f"可用项目: {', '.join(names)}\n"
            "提示: 名称需精确或唯一匹配。"
        )
    return f"未找到项目: {arg}（当前无已注册项目，请先用 /项目 新建 创建）"


def format_model_reply(
    orchestrator: "ButlerOrchestrator",
    session_registry: Any,
    session_key: str,
    arg: str,
) -> str:
    """/模型 [provider/model]: 查看或切换当前模型. 副作用: model 变化时 reset session."""
    from butler.model_resolve import handle_model_command

    proj = orchestrator.project_manager.get_current(session_key=session_key)
    proj_name = (
        orchestrator.project_manager.resolve_active_project_name(
            session_key=session_key,
        )
        or None
    )
    reply, reset_loop = handle_model_command(
        arg,
        settings=orchestrator._settings,
        project=proj,
        project_label=proj_name,
    )
    if reset_loop:
        session_registry.reset(session_key)
        from butler.tools.tool_audit import reset_tool_audit_events

        reset_tool_audit_events(session_key)
    return reply


def format_new_session_reply(
    orchestrator: "ButlerOrchestrator",
    session_registry: Any,
    sessions: dict,
    session_key: str,
) -> str:
    """/新对话: 清空当前会话状态, 11+ 项清理 + 触发 session end 钩子."""
    from butler.session.new_session import handle_new_session_command

    loop = sessions.get(session_key)
    session_registry.reset(session_key, skip_finalize=True)
    from butler.tools.tool_audit import reset_tool_audit_events

    reset_tool_audit_events(session_key)
    from butler.report import clear_report_cache

    clear_report_cache(session_key)
    from butler.plan.mode import clear_plan_mode

    clear_plan_mode(session_key)
    try:
        from butler.hooks.telemetry import reset_hook_telemetry
        from butler.gateway.completion_telemetry import reset_completion_telemetry

        reset_hook_telemetry(session_key)
        reset_completion_telemetry(session_key)
        from butler.core.read_state import reset_read_state
        from butler.gateway.message_queue import reset_queue
        from butler.gateway.queue_settings import clear_session_override
        from butler.human_gate import clear_session_gates
        from butler.core.instruction_walkup import reset_instruction_claims

        reset_read_state(session_key)
        reset_queue(session_key)
        clear_session_override(session_key)
        clear_session_gates(session_key)
        reset_instruction_claims(session_key=session_key)
        from butler.core.goal_loop import clear_state as clear_goal_loop
        from butler.core.compaction_checkpoint import clear_checkpoint

        clear_goal_loop(session_key)
        clear_checkpoint(session_key)
    except Exception as exc:
        logger.debug("Session cleanup for new session skipped: %s", exc)
    return handle_new_session_command(orchestrator, session_key, loop)


def _cmd_switch_project(ctx: CommandContext) -> Optional[str]:
    """handler for /切换 — 切换本 chat 的活跃项目.

    owner-gate-opt-out: per-chat 会话级切换, 用户自有项目偏好, 非 owner 操作
    """
    return format_switch_project_reply(
        ctx.orchestrator,
        ctx.session_registry,
        ctx.session_key,
        ctx.arg,
        ctx.platform,
    )


def _cmd_model_select(ctx: CommandContext) -> Optional[str]:
    """handler for /模型 — 查看或切换当前模型.

    owner-gate-opt-out: per-session 模型偏好, 用户自有选择, 非 owner 操作
    """
    return format_model_reply(
        ctx.orchestrator,
        ctx.session_registry,
        ctx.session_key,
        ctx.arg,
    )


def _cmd_new_session(ctx: CommandContext) -> Optional[str]:
    """handler for /新对话 — 重置当前会话状态.

    owner-gate-opt-out: 清空用户自己的会话状态, 非 owner 操作
    """
    sessions = ctx.session_registry.sessions
    return format_new_session_reply(
        ctx.orchestrator,
        ctx.session_registry,
        sessions,
        ctx.session_key,
    )


_DIALOG_COMMANDS = [
    CommandDef("/steer", ("/指引",), "对话控制", "插入引导消息", handler=_cmd_steer),
    CommandDef("/queue", (), "对话控制", "入站队列模式", handler=_cmd_queue),
    CommandDef("/确认", ("/approve",), "规划模式", "确认 workflow 步骤", handler=_cmd_approve),
    CommandDef("/取消", ("/cancel",), "规划模式", "取消 workflow 步骤", handler=_cmd_cancel),
    CommandDef("/循环", ("/loop",), "对话控制", "启动目标循环模式", handler=_cmd_goal_loop),
    CommandDef("/停止循环", ("/stoploop",), "对话控制", "停止目标循环", handler=_cmd_stop_goal_loop),
    CommandDef("/计划", ("/plan", "/规划"), "规划模式", "进入规划模式", handler=_cmd_plan_mode),
    CommandDef("/执行", ("/exit-plan", "/退出规划"), "规划模式", "退出规划，开始执行", handler=_cmd_exit_plan),
    # Sprint 16 TST-10-5 第七批
    CommandDef("/切换", ("/switch",), "项目管理", "切换当前项目", handler=_cmd_switch_project),
    CommandDef("/模型", ("/model",), "模型", "查看/切换当前模型", handler=_cmd_model_select),
    CommandDef("/新对话", ("/new",), "对话控制", "重置当前会话", handler=_cmd_new_session),
]

for _cmd in _DIALOG_COMMANDS:
    register(_cmd)

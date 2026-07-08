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

from typing import TYPE_CHECKING, Any, Optional

from butler.gateway.command_registry import (
    CommandContext,
    CommandDef,
    register,
    require_owner,
)
from butler.core.goal_loop import start_goal_loop, stop_goal_loop
from butler.core.steer import format_steer_gateway_reply, is_run_active, steer
from butler.gateway.commands.dialog_commands_ops import (
    cleanup_new_session_state_safe,
    format_project_slug_hint_safe,
    format_project_switch_brief_safe,
    record_session_reset_safe,
)
from butler.gateway.queue_settings import apply_queue_command
from butler.human_gate import resolve_human_gate_message
from butler.model_resolve import handle_model_command
from butler.plan.mode import (
    clear_plan_mode,
    format_plan_mode_status,
    set_plan_mode,
)
from butler.project.lead import lead_mode_switch_suffix
from butler.report import clear_report_cache
from butler.session.new_session import handle_new_session_command
from butler.tools.tool_audit import reset_tool_audit_events

if TYPE_CHECKING:
    from butler.orchestrator import ButlerOrchestrator

def _as_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _cmd_steer(ctx: CommandContext) -> Optional[str]:
    gate = require_owner(ctx)
    if gate is not None:
        return str(gate)

    active = is_run_active(ctx.session_key)
    accepted = bool(active and steer(ctx.arg, session_key=ctx.session_key))
    return _as_str(format_steer_gateway_reply(accepted=accepted, active=active))


def _cmd_queue(ctx: CommandContext) -> Optional[str]:
    gate = require_owner(ctx)
    if gate is not None:
        return str(gate)

    return _as_str(apply_queue_command(ctx.session_key, ctx.arg))


def _cmd_approve(ctx: CommandContext) -> Optional[str]:
    gate = require_owner(ctx)
    if gate is not None:
        return str(gate)

    return _as_str(
        resolve_human_gate_message(ctx.session_key, "确认", owner_verified=True)
    ) or "当前没有待确认的工作流步骤。"


def _cmd_cancel(ctx: CommandContext) -> Optional[str]:
    gate = require_owner(ctx)
    if gate is not None:
        return str(gate)

    return _as_str(
        resolve_human_gate_message(ctx.session_key, "取消", owner_verified=True)
    ) or "当前没有待确认的工作流步骤。"


def _cmd_goal_loop(ctx: CommandContext) -> Optional[str]:
    gate = require_owner(ctx)
    if gate is not None:
        return str(gate)

    return _as_str(start_goal_loop(ctx.session_key, ctx.arg))


def _cmd_stop_goal_loop(ctx: CommandContext) -> Optional[str]:
    gate = require_owner(ctx)
    if gate is not None:
        return str(gate)

    return _as_str(stop_goal_loop(ctx.session_key))


def _cmd_plan_mode(ctx: CommandContext) -> Optional[str]:
    gate = require_owner(ctx)
    if gate is not None:
        return str(gate)

    arg_l = (ctx.arg or "").strip().lower()
    if arg_l in ("off", "exit", "执行", "退出", "关闭"):
        clear_plan_mode(ctx.session_key)
        ctx.reset_loop()
        return "已退出规划模式，可以委派与写入。"
    set_plan_mode(ctx.session_key, True)
    ctx.reset_loop()
    return _as_str(format_plan_mode_status(ctx.session_key))


def _cmd_exit_plan(ctx: CommandContext) -> Optional[str]:
    gate = require_owner(ctx)
    if gate is not None:
        return str(gate)

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
        lead_note = lead_mode_switch_suffix(new_name)
        brief = format_project_switch_brief_safe(orchestrator, session_key, new_name)
        return (
            f"已切换到项目: {new_name}\n"
            "（下一条消息起使用新项目工具与 workspace。）"
            f"{extra}{lead_note}{brief}"
        )
    available = pm.list_projects()
    if available:
        names = [p.name for p in available]
        slug_hint = format_project_slug_hint_safe(available)
        suggestions = pm.suggest_project_names(arg, limit=3)
        body = [f"未找到项目: {arg}"]
        if suggestions:
            primary = suggestions[0]
            body.append(f"你是不是指：**{primary}**？")
            body.append(f"回复：/切换 {primary}")
            if len(suggestions) > 1:
                body.append(f"其他可能: {', '.join(suggestions[1:])}")
        body.append(f"\n可用项目: {', '.join(names)}")
        body.append("提示: 可用显示名或项目目录名（如 LingWen1）。")
        if slug_hint:
            body.append(slug_hint)
        return "\n".join(body)
    return f"未找到项目: {arg}（当前无已注册项目，请先用 /项目 新建 创建）"


def format_model_reply(
    orchestrator: "ButlerOrchestrator",
    session_registry: Any,
    session_key: str,
    arg: str,
) -> str:
    """/模型 [provider/model]: 查看或切换当前模型. 副作用: model 变化时 reset session."""
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
        reset_tool_audit_events(session_key)
    return str(reply)


def format_new_session_reply(
    orchestrator: "ButlerOrchestrator",
    session_registry: Any,
    sessions: dict[str, Any],
    session_key: str,
) -> str:
    """/新对话: 清空当前会话状态, 11+ 项清理 + 触发 session end 钩子."""
    loop = sessions.get(session_key)

    record_session_reset_safe(session_key, reason="new")
    session_registry.reset(session_key, skip_finalize=True)
    reset_tool_audit_events(session_key)
    clear_report_cache(session_key)
    clear_plan_mode(session_key)
    cleanup_new_session_state_safe(session_key)
    return str(handle_new_session_command(orchestrator, session_key, loop))


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
    CommandDef("/新对话", ("/new", "/新会话"), "对话控制", "重置当前会话", handler=_cmd_new_session),
]

for _cmd in _DIALOG_COMMANDS:
    register(_cmd)

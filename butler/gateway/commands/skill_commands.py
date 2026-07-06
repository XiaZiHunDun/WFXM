"""Gateway slash commands for skill pending queue and /技能学习."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Optional, cast

from butler.gateway.command_registry import CommandContext, CommandDef, register
from butler.gateway.owner_gate import is_gateway_owner, owner_required_message
from butler.skills.learn import run_skill_learn

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from butler.orchestrator import ButlerOrchestrator


def format_skill_pending_list(orchestrator: "ButlerOrchestrator") -> str:
    from butler.skills.write_approval import format_skill_pending_lines

    lines = format_skill_pending_lines()
    if not lines:
        return "当前没有待批准的技能。"
    return "\n".join(lines)


def handle_skill_pending_command(
    orchestrator: "ButlerOrchestrator",
    cmd: str,
    arg: str,
    *,
    platform: str = "",
    external_id: str | None = None,
    session_key: str = "",
) -> Optional[str]:
    if cmd in ("/技能待审", "/pending-skill", "/待审技能"):
        return format_skill_pending_list(orchestrator)

    if cmd in ("/拒绝技能", "/reject-skill"):
        return _handle_reject_skill(arg)

    if cmd not in ("/批准技能", "/approve-skill"):
        return None

    if not is_gateway_owner(
        platform=platform, external_id=external_id, session_key=session_key
    ):
        return cast(str, owner_required_message())

    return _handle_approve_skill(orchestrator, arg)


def _skill_manager(orchestrator: "ButlerOrchestrator") -> Any:
    sm = getattr(orchestrator, "_skill_manager", None) or getattr(
        orchestrator, "skill_manager", None
    )
    if sm is not None:
        return sm
    from butler.orchestrator.skill_bridge import rebuild_skill_router

    rebuild_skill_router(orchestrator)
    return orchestrator._skill_manager


def _handle_approve_skill(orchestrator: "ButlerOrchestrator", arg: str) -> str:
    from butler.skills.write_approval import (
        approve_all_skill_pending,
        approve_skill_pending,
        list_skill_pending,
    )

    sm = _skill_manager(orchestrator)
    key = (arg or "").strip().lower()
    if key in ("全部", "all", "*"):
        count = approve_all_skill_pending(sm)
        return f"已批准 {count} 条待审技能。"

    if not arg.strip():
        return "用法: /批准技能 <序号>  或  /批准技能 全部\n先发送 /技能待审 查看列表。"

    try:
        idx = int(arg.strip()) - 1
    except ValueError:
        return "序号必须是数字。例: /批准技能 1"

    pending = list_skill_pending()
    if not pending:
        return "没有待批准技能。"
    if not (0 <= idx < len(pending)):
        return f"序号超出范围（1–{len(pending)}）。"

    result = approve_skill_pending(idx, sm)
    if result.get("ok"):
        return f"已批准技能「{result.get('name', '?')}」（{result.get('outcome', 'created')}）。"
    return f"批准失败: {result.get('error', 'unknown')}"


def _handle_reject_skill(arg: str) -> str:
    from butler.skills.write_approval import list_skill_pending, reject_all_skill_pending, reject_skill_pending

    key = (arg or "").strip().lower()
    if key in ("全部", "all", "*"):
        count = reject_all_skill_pending()
        return f"已拒绝 {count} 条待审技能。"

    if not arg.strip():
        return "用法: /拒绝技能 <序号>  或  /拒绝技能 全部"

    try:
        idx = int(arg.strip()) - 1
    except ValueError:
        return "序号必须是数字。"

    if reject_skill_pending(idx):
        return f"已拒绝第 {idx + 1} 条技能。"
    return "拒绝失败（条目可能已被处理）。"


def handle_skill_learn(
    orchestrator: "ButlerOrchestrator",
    description: str,
    *,
    platform: str = "",
    external_id: str | None = None,
    session_key: str = "",
) -> str:
    if not is_gateway_owner(
        platform=platform, external_id=external_id, session_key=session_key
    ):
        return cast(str, owner_required_message())

    desc = (description or "").strip()
    if len(desc) < 8:
        return "用法: /技能学习 <描述>（至少 8 字）"

    sm = _skill_manager(orchestrator)
    result = run_skill_learn(desc, sm)
    if not result.get("ok"):
        return str(result.get("error") or "技能学习失败")
    return str(result.get("message") or "技能学习完成")


def _cmd_skill_pending_list(ctx: CommandContext) -> Optional[str]:
    return format_skill_pending_list(ctx.orchestrator)


def _cmd_skill_approve(ctx: CommandContext) -> Optional[str]:
    return handle_skill_pending_command(
        ctx.orchestrator,
        "/批准技能",
        ctx.arg,
        platform=ctx.platform,
        external_id=ctx.external_id,
        session_key=ctx.session_key,
    )


def _cmd_skill_reject(ctx: CommandContext) -> Optional[str]:
    return handle_skill_pending_command(
        ctx.orchestrator,
        "/拒绝技能",
        ctx.arg,
        platform=ctx.platform,
        external_id=ctx.external_id,
        session_key=ctx.session_key,
    )


def _cmd_skill_learn(ctx: CommandContext) -> Optional[str]:
    return handle_skill_learn(
        ctx.orchestrator,
        ctx.arg,
        platform=ctx.platform,
        external_id=ctx.external_id,
        session_key=ctx.session_key,
    )


_SKILL_COMMANDS: list[CommandDef] = [
    CommandDef(
        "/技能待审",
        ("/pending-skill", "/待审技能"),
        "技能",
        "查看待批准技能",
        handler=_cmd_skill_pending_list,
    ),
    CommandDef(
        "/批准技能",
        ("/approve-skill",),
        "技能",
        "批准待审技能（Owner only）",
        handler=_cmd_skill_approve,
    ),
    CommandDef(
        "/拒绝技能",
        ("/reject-skill",),
        "技能",
        "拒绝待审技能",
        handler=_cmd_skill_reject,
    ),
    CommandDef(
        "/技能学习",
        ("/skill-learn", "/learn"),
        "技能",
        "受控技能学习（入待审，Owner only）",
        handler=_cmd_skill_learn,
    ),
]


def register_skill_commands() -> None:
    for cmd in _SKILL_COMMANDS:
        register(cmd)


register_skill_commands()

__all__ = [
    "format_skill_pending_list",
    "handle_skill_learn",
    "handle_skill_pending_command",
    "register_skill_commands",
]

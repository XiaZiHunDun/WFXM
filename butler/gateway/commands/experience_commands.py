"""D3-6 experience mining WeChat commands."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from butler.gateway.command_registry import CommandContext, CommandDef, register, require_owner


def _workspace_from_ctx(ctx: CommandContext) -> Path | None:
    from butler.gateway.commands.experience_commands_ops import workspace_from_command_ctx_safe

    return workspace_from_command_ctx_safe(ctx)


def _cmd_experience_mine(ctx: CommandContext) -> Optional[str]:
    gate = require_owner(ctx)
    if gate:
        return gate

    from butler.memory.experience_mining import (
        approve_pending,
        format_pending_lines,
        format_pipeline_report,
        run_pipeline,
    )

    arg = (ctx.arg or "").strip().lower()
    if arg in ("pending", "待审", "list"):
        return "\n".join(format_pending_lines(limit=12))

    if arg.startswith("approve") or arg.startswith("批准"):
        tokens = arg.split()
        approve_all = "all" in tokens or "全部" in tokens
        ids = [t for t in tokens[1:] if t not in ("all", "全部")]
        counts = approve_pending(None if approve_all else ids, approve_all=approve_all)
        return (
            f"经验批准完成\n"
            f"  批准: {counts['approved']}\n"
            f"  入库: {counts['added']}\n"
            f"  跳过: {counts['skipped']}"
        )

    ws = _workspace_from_ctx(ctx)
    result = run_pipeline(ws)
    return format_pipeline_report(result)


_EXPERIENCE_COMMANDS = [
    CommandDef(
        "/经验挖掘",
        ("/mine-experience", "/experience-mine"),
        "开发工具",
        "挖掘候选经验 → 定理审查 → 待审/入库",
        handler=_cmd_experience_mine,
    ),
]


def register_experience_commands() -> None:
    for cmd in _EXPERIENCE_COMMANDS:
        register(cmd)


register_experience_commands()

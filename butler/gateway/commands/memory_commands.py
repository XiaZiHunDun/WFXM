"""Sprint 16 TST-10-5: memory pending / triplet graph 4 个 inline 命令迁移到 registry handler.

迁移的命令:
  - /记忆图谱 (/memory-graph, /三元组)         → _cmd_memory_graph
  - /记忆待审 (/pending-memory, /待审记忆)      → _cmd_memory_pending_list
  - /拒绝记忆 (/reject-memory, /拒绝)          → _cmd_memory_reject
  - /批准记忆 (/approve-memory, /批准)          → _cmd_memory_approve (含 owner gate)

Sprint 11 SEC-11-2: /批准记忆 永久写入 MEMORY.md, 仅 Owner 可批准。
"""

from __future__ import annotations

from typing import Optional

from butler.gateway.command_registry import CommandContext, CommandDef, register
from butler.gateway.owner_gate import is_gateway_owner, owner_required_message


def _cmd_memory_graph(ctx: CommandContext) -> Optional[str]:
    from butler.gateway.memory_commands import format_memory_triplet_graph

    return format_memory_triplet_graph(ctx.orchestrator)


def _cmd_memory_pending_list(ctx: CommandContext) -> Optional[str]:
    from butler.gateway.memory_commands import format_pending_memory_list

    return format_pending_memory_list(ctx.orchestrator)


def _cmd_memory_reject(ctx: CommandContext) -> Optional[str]:
    from butler.gateway.memory_commands import handle_memory_pending_command

    return handle_memory_pending_command(
        ctx.orchestrator,
        "/拒绝记忆",
        ctx.arg,
        platform=ctx.platform,
        external_id=ctx.external_id,
        session_key=ctx.session_key,
    )


def _cmd_memory_approve(ctx: CommandContext) -> Optional[str]:
    if not is_gateway_owner(
        platform=ctx.platform, external_id=ctx.external_id, session_key=ctx.session_key
    ):
        return owner_required_message()
    from butler.gateway.memory_commands import handle_memory_pending_command

    return handle_memory_pending_command(
        ctx.orchestrator,
        "/批准记忆",
        ctx.arg,
        platform=ctx.platform,
        external_id=ctx.external_id,
        session_key=ctx.session_key,
    )


_MEMORY_COMMANDS: list[CommandDef] = [
    CommandDef(
        "/记忆图谱",
        ("/memory-graph", "/三元组"),
        "记忆",
        "查看三元组关系图",
        handler=_cmd_memory_graph,
    ),
    CommandDef(
        "/记忆待审",
        ("/pending-memory", "/待审记忆"),
        "记忆",
        "查看待审批记忆",
        handler=_cmd_memory_pending_list,
    ),
    CommandDef(
        "/拒绝记忆",
        ("/reject-memory", "/拒绝"),
        "记忆",
        "拒绝待审记忆（不入正式章节）",
        handler=_cmd_memory_reject,
    ),
    CommandDef(
        "/批准记忆",
        ("/approve-memory", "/批准"),
        "记忆",
        "批准待审记忆（写入正式章节，Owner only）",
        handler=_cmd_memory_approve,
    ),
]


def register_memory_commands() -> None:
    """幂等注册 — 重复调用安全。"""
    for cmd in _MEMORY_COMMANDS:
        register(cmd)


# Import 时即注册, 与 lifecycle/dialog/info 命令的 import-side-effect 模式一致。
register_memory_commands()

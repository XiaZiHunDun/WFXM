"""Sprint 16 TST-10-5 第三批: runtime jobs 命令迁移到 registry handler.

迁移的命令:
  - /定时 (/runtime, /定时任务)            → _cmd_runtime_jobs_list
  - /批准运行 (/approve-run, /批准任务)     → _cmd_runtime_approve_run (含 owner gate)
  - /运行 (/run-job, /运行任务)             → _cmd_runtime_run (含 owner gate)

Sprint 11 SEC-11-1: /批准运行 /运行 路径加 owner gate（改盘操作）。
"""

from __future__ import annotations

from typing import Optional

from butler.gateway.command_registry import CommandContext, CommandDef, register
from butler.gateway.owner_gate import is_gateway_owner, owner_required_message


def _cmd_runtime_jobs_list(ctx: CommandContext) -> Optional[str]:
    from butler.gateway.runtime_commands import handle_runtime_command

    return handle_runtime_command(
        ctx.orchestrator,
        "/定时",
        ctx.arg,
        platform=ctx.platform,
        external_id=ctx.external_id,
        session_key=ctx.session_key,
    )


def _cmd_runtime_approve_run(ctx: CommandContext) -> Optional[str]:
    if not is_gateway_owner(
        platform=ctx.platform, external_id=ctx.external_id, session_key=ctx.session_key
    ):
        return owner_required_message()
    from butler.gateway.runtime_commands import handle_runtime_command

    return handle_runtime_command(
        ctx.orchestrator,
        "/批准运行",
        ctx.arg,
        platform=ctx.platform,
        external_id=ctx.external_id,
        session_key=ctx.session_key,
    )


def _cmd_runtime_run(ctx: CommandContext) -> Optional[str]:
    if not is_gateway_owner(
        platform=ctx.platform, external_id=ctx.external_id, session_key=ctx.session_key
    ):
        return owner_required_message()
    from butler.gateway.runtime_commands import handle_runtime_command

    return handle_runtime_command(
        ctx.orchestrator,
        "/运行",
        ctx.arg,
        platform=ctx.platform,
        external_id=ctx.external_id,
        session_key=ctx.session_key,
    )


_RUNTIME_COMMANDS: list[CommandDef] = [
    CommandDef(
        "/定时",
        ("/runtime", "/定时任务"),
        "系统管理",
        "查看定时任务",
        handler=_cmd_runtime_jobs_list,
    ),
    CommandDef(
        "/批准运行",
        ("/approve-run", "/批准任务"),
        "系统管理",
        "批准并执行定时任务（Owner only）",
        handler=_cmd_runtime_approve_run,
    ),
    CommandDef(
        "/运行",
        ("/run-job", "/运行任务"),
        "系统管理",
        "执行定时任务（Owner only）",
        handler=_cmd_runtime_run,
    ),
]


def register_runtime_commands() -> None:
    """幂等注册 — 重复调用安全。"""
    for cmd in _RUNTIME_COMMANDS:
        register(cmd)


# Import 时即注册
register_runtime_commands()

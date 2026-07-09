"""Sprint 16 TST-10-5 第五批: 项目 / 状态 inline 命令迁移.

迁移 4 个命令 (2 个注册名 + 2 个 /项目 子命令走的也是同一个 /项目 handler):

  - /项目   (/projects)                → _cmd_project_list
  - /状态   (/status)                   → _cmd_butler_status
  - /项目 新建     (子命令, arg="新建 ...")     → 经 /项目 handler 委派
  - /项目 体检     (子命令, arg="体检")         → 经 /项目 handler 委派
  - /项目 register (子命令, arg="register ...") → 经 /项目 handler 委派

迁移要点:
  - 内联块 32 行 (项目列表 + 委派 onboard) 抽到 format_project_list().
  - 内联块 31 行 (Butler 状态汇总) 抽到 format_butler_status().
  - /项目 新建 和 /项目 体检 是 /项目 的子命令, 通过 ctx.arg 区分, 不再
    作为独立 CommandDef 注册 (它们从 default 列表移除, 因 cmd 永远是 /项目,
    单独注册从未被 dispatch 命中).
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Optional, cast

from butler.gateway.command_registry import (
    CommandContext,
    CommandDef,
    register,
    require_owner,
)

if TYPE_CHECKING:
    from butler.orchestrator import ButlerOrchestrator


def format_project_list(
    orchestrator: "ButlerOrchestrator",
    cmd: str,
    arg: str,
    *,
    session_key: str,
    platform: str = "unknown",
    external_id: str | None = None,
) -> str:
    """List all projects, or dispatch to /项目 新建|体检|register onboarding."""
    from butler.gateway.commands.project_handlers import handle_project_onboarding_command

    onboard = handle_project_onboarding_command(
        orchestrator,
        cmd,
        arg,
        session_key=session_key,
        platform=platform,
        external_id=external_id,
    )
    if onboard is not None:
        return cast(str, onboard)

    projects = orchestrator.project_manager.list_projects()
    if not projects:
        return "暂无项目。"
    current = orchestrator.project_manager.resolve_active_project_name(
        session_key=session_key,
    )
    lines = [
        "项目列表（* 当前）",
        "  /项目 新建 <slug> [模板]",
        "  /项目 register <显示名> <路径>",
        "  /项目 体检",
        "",
    ]
    for p in sorted(projects, key=lambda x: x.name):
        mark = "* " if p.name == current else "  "
        pack = getattr(p, "pack", "") or ""
        extra = f" pack={pack}" if pack else ""
        lines.append(f"{mark}{p.name} ({p.type}{extra}) — {p.description}")
    return "\n".join(lines)


def format_butler_status(
    orchestrator: "ButlerOrchestrator",
    session_key: str,
) -> str:
    """Format Butler runtime status: project, provider, lead/butler role, plan mode."""
    from butler.plan.mode import format_plan_mode_status
    from butler.project.lead import gateway_loop_role, is_lead_project
    from butler.project.meta import format_project_meta_lines

    s = orchestrator._settings
    pm = orchestrator.project_manager
    current = pm.resolve_active_project_name(session_key=session_key) or "(无)"
    proj = pm.get_current(session_key=session_key)
    default_proj = os.getenv("BUTLER_DEFAULT_PROJECT", "").strip() or "(未设置)"
    lines = [
        "Butler 状态",
    ]
    from butler.gateway.commands.project_commands_ops import format_owner_status_header_lines_safe

    header_lines = format_owner_status_header_lines_safe(orchestrator, session_key)
    if header_lines:
        lines.extend(header_lines)
        lines.append("")
    s = orchestrator._settings
    lines.append(f"  管家: {s.butler_name}")
    lines.append(f"  当前项目: {current}")
    lines.append(f"  环境默认项目: {default_proj}")
    lines.append(f"  默认 Provider: {s.default_provider}")
    if proj is not None:
        lines.append(
            f"  对话引擎: {'项目 Lead（厂长）' if is_lead_project(proj.name, project=proj) else '管家 Butler'}"
        )
        lines.extend(format_project_meta_lines(proj))
    elif current != "(无)":
        lines.append(f"  对话引擎: {gateway_loop_role(current)}")
    else:
        lines.append("  对话引擎: 个人管家 Butler（未绑定项目，发 /切换 进入厂长）")
    if proj is not None:
        from butler.project.maturity import format_maturity_status_line

        lines.append(format_maturity_status_line(proj.name))
    lines.append(f"  {format_plan_mode_status(session_key).replace(chr(10), ' ')}")
    return "\n".join(lines)


def _cmd_project_list(ctx: CommandContext) -> Optional[str]:
    """handler for /项目 — 包含 /项目 新建|体检|register 子命令委派."""
    gate = require_owner(ctx)
    if gate:
        return cast(str, gate)
    return format_project_list(
        ctx.orchestrator,
        ctx.cmd,
        ctx.arg,
        session_key=ctx.session_key,
        platform=ctx.platform,
        external_id=ctx.external_id,
    )


def _cmd_butler_status(ctx: CommandContext) -> Optional[str]:
    """handler for /状态 — 当前项目/Provider/角色/规划模式 概览."""
    gate = require_owner(ctx)
    if gate:
        return cast(str, gate)
    return format_butler_status(ctx.orchestrator, ctx.session_key)


_PROJECT_COMMANDS: list[CommandDef] = [
    CommandDef(
        "/项目",
        ("/projects",),
        "项目管理",
        "列出所有项目 (含 /项目 新建|register|体检 子命令)",
        handler=_cmd_project_list,
    ),
    CommandDef(
        "/状态",
        ("/status",),
        "项目管理",
        "当前项目与管家状态",
        handler=_cmd_butler_status,
    ),
]


def register_project_commands() -> None:
    """idempotent 注册 — 覆盖 default list 中的无 handler 版本."""
    for cmd in _PROJECT_COMMANDS:
        register(cmd)


# Import 时即注册, 与 lifecycle/dialog/info/memory/runtime/dev 模式一致。
register_project_commands()

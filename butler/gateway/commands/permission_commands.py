"""Sprint 16 TST-10-5 第六批: 权限安全 inline 命令迁移.

迁移 5 个 inline 命令到 registry handler:
  - /权限     (/perms)                       → _cmd_perm_list
  - /批准一次                                  → _cmd_perm_once
  - /始终允许  (/always-allow)                → _cmd_perm_always
  - /批准执行  (/approve-exec)                → _cmd_perm_exec
  - /批准模式  (/approve-pattern)             → _cmd_perm_pattern

迁移要点:
  - 原 permission/terminal 块在 message_handler.handle_message 中
    (slash dispatch 之前, line 421-461). 5 个 handler 集中到 _cmd_perm_*.
  - 行为差异: 旧 try/except logger.debug 吞异常, 新走 registry 集中处理
    (logger.error + 返 "命令执行异常: ..."). 失败时用户可见.
  - Owner gate 仍每个 handler 入口检查 (与旧版一致, 保持 Sprint 11 SEC 行为).
"""

from __future__ import annotations

from typing import Optional

from butler.gateway.command_registry import (
    CommandContext,
    CommandDef,
    register,
    require_owner,
)


def _cmd_perm_list(ctx: CommandContext) -> Optional[str]:
    """handler for /权限 — 列出本会话 always-allow 记录."""
    gate = require_owner(ctx)
    if gate is not None:
        return gate
    from butler.permissions.approvals import list_always

    rows = list_always(ctx.session_key)
    if not rows:
        return "当前会话无「始终允许」记录。"
    lines = ["始终允许:"]
    for row in rows:
        lines.append(
            f"  · {row.get('permission')} tool={row.get('tool')} pattern={row.get('pattern')}"
        )
    return "\n".join(lines)


def _cmd_perm_once(ctx: CommandContext) -> Optional[str]:
    """handler for /批准一次 <fingerprint>."""
    gate = require_owner(ctx)
    if gate is not None:
        return gate
    from butler.permissions.approvals import grant_once

    return grant_once(ctx.session_key, fingerprint=ctx.arg.strip())


def _cmd_perm_always(ctx: CommandContext) -> Optional[str]:
    """handler for /始终允许 <spec> — 永久放行某类操作."""
    gate = require_owner(ctx)
    if gate is not None:
        return gate

    spec = (ctx.arg or "").strip()
    if not spec:
        return (
            "用法：/始终允许 <权限名> 或 /始终允许 write_file:secrets/*\n"
            "示例：/始终允许 external_directory · /始终允许 doom_loop · "
            "/始终允许 rule:read_file:AGENTS.md"
        )

    from butler.permissions.approvals import grant_always

    tool = "*"
    pattern = "*"
    permission = spec
    if ":" in spec:
        head, tail = spec.split(":", 1)
        permission = head.strip() or "rule"
        if "." in tail or "/" in tail or "*" in tail:
            # rule:<tool>:<pattern>
            tool = permission
            pattern = tail.strip() or "*"
            permission = "rule"
        else:
            # <tool>:<pattern>
            tool = head.strip() or "*"
            pattern = tail.strip() or "*"
    return grant_always(
        ctx.session_key,
        permission=permission,
        tool=tool,
        pattern=pattern,
    )


def _cmd_perm_exec(ctx: CommandContext) -> Optional[str]:
    """handler for /批准执行 <cmd> — 放行 terminal 命令 5 分钟."""
    gate = require_owner(ctx)
    if gate is not None:
        return gate
    cmd = ctx.arg.strip()
    if not cmd:
        return "用法: /批准执行 <terminal 命令>"
    from butler.tools.terminal_approval import store_approval

    store_approval(cmd, session_key=ctx.session_key)
    return f"已批准 terminal 命令（5 分钟内有效）:\n{cmd[:200]}"


def _cmd_perm_pattern(ctx: CommandContext) -> Optional[str]:
    """handler for /批准模式 <pattern> — 24h 内同类 terminal 命令放行."""
    gate = require_owner(ctx)
    if gate is not None:
        return gate
    pat = ctx.arg.strip()
    if not pat:
        return "用法: /批准模式 <rm_rf|curl_pipe_sh|chmod_777|...>"
    from butler.tools.terminal_pattern_approval import approve_pattern

    approve_pattern(ctx.session_key, pat)
    return f"已批准本会话 terminal 危险模式「{pat}」（24h 内同类命令可放行）。"


def _cmd_revoke_always(ctx: CommandContext) -> Optional[str]:
    """Sprint 24 P1-3.2: /撤销批准 <permission> [tool] [pattern]."""
    gate = require_owner(ctx)
    if gate is not None:
        return gate
    arg = (ctx.arg or "").strip()
    if not arg:
        return "用法: /撤销批准 <permission> [tool] [pattern]"
    parts = arg.split()
    perm = parts[0] if len(parts) >= 1 else ""
    tool = parts[1] if len(parts) >= 2 else ""
    pat = parts[2] if len(parts) >= 3 else ""
    from butler.permissions.approvals import revoke_always
    return revoke_always(ctx.session_key, permission=perm, tool=tool, pattern=pat)


def _cmd_clear_always(ctx: CommandContext) -> Optional[str]:
    """Sprint 24 P1-3.2: /清除始终允许 — 清空 session 所有 always 记录."""
    gate = require_owner(ctx)
    if gate is not None:
        return gate
    from butler.permissions.approvals import clear_always
    return clear_always(ctx.session_key)


_PERMISSION_COMMANDS: list[CommandDef] = [
    CommandDef(
        "/权限",
        ("/perms",),
        "权限安全",
        "查看当前权限状态",
        handler=_cmd_perm_list,
    ),
    CommandDef(
        "/批准一次",
        (),
        "权限安全",
        "放行一次被拦截的操作",
        handler=_cmd_perm_once,
    ),
    CommandDef(
        "/始终允许",
        ("/always-allow",),
        "权限安全",
        "永久放行某类操作",
        handler=_cmd_perm_always,
    ),
    CommandDef(
        "/批准执行",
        ("/approve-exec",),
        "权限安全",
        "批准 terminal 命令",
        handler=_cmd_perm_exec,
    ),
    CommandDef(
        "/批准模式",
        ("/approve-pattern",),
        "权限安全",
        "按模式批准（24h 有效）",
        handler=_cmd_perm_pattern,
    ),
    CommandDef(
        "/撤销批准",
        (),
        "权限安全",
        "撤销已设置的始终允许规则",
        handler=_cmd_revoke_always,
    ),
    CommandDef(
        "/清除始终允许",
        (),
        "权限安全",
        "清空当前会话所有始终允许",
        handler=_cmd_clear_always,
    ),
]


def register_permission_commands() -> None:
    """idempotent 注册 — 覆盖 default list 中的无 handler 版本."""
    for cmd in _PERMISSION_COMMANDS:
        register(cmd)


# Import 时即注册, 与 lifecycle/dialog/info/memory/runtime/dev/project 模式一致。
register_permission_commands()

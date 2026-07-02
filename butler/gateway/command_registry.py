"""Unified command registry for Butler gateway slash commands.

Supports two tiers of command handling:

1. **Registered handlers** — ``CommandDef.handler`` is a callable that receives
   a ``CommandContext`` and returns ``str | None``.  These are resolved via
   ``dispatch()`` and bypass the legacy if/elif chain.

2. **Legacy inline** — commands without a handler fall through to
   ``ButlerMessageHandler._handle_command``'s if/elif chain.  New commands
   should always use tier 1.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Optional

if TYPE_CHECKING:
    from butler.orchestrator import ButlerOrchestrator
    from butler.gateway.session_registry import GatewaySessionRegistry

logger = logging.getLogger(__name__)


@dataclass
class CommandContext:
    """Immutable bag of state passed to every registered command handler."""

    cmd: str
    arg: str
    session_key: str
    platform: str
    external_id: str | None
    orchestrator: Any
    session_registry: Any

    def reset_loop(self) -> None:
        """Convenience: destroy the current session's AgentLoop."""
        self.session_registry.reset(self.session_key)


CommandHandler = Callable[[CommandContext], Optional[str]]


def require_owner(ctx: CommandContext) -> Optional[str]:
    """Sprint 18-1 真源: 5 个 commands/*.py 共享 owner-gate 守门.

    非 owner 返 owner_required_message, owner 返 None (继续执行).
    行为完全等价于原先 dialog/info/project/permission/lifecycle 各自的本地
    _require_owner / _check_owner_or_return, 单一真源便于改 owner gate 规则.
    """
    return require_owner_kw(
        platform=ctx.platform, external_id=ctx.external_id, session_key=ctx.session_key
    )


def require_owner_kw(
    platform: str, external_id: str | None, session_key: str
) -> Optional[str]:
    """Sprint 19-4 SEC-19-4: kwargs 变体真源, 供 legacy 不走 CommandContext 的
    调用方 (registry_commands 等) 使用. 行为与 require_owner 一致.
    """
    # 延迟导入避免 module 加载顺序耦合 (owner_gate 不依赖本模块, 这里是单向引用)
    from butler.gateway.owner_gate import is_gateway_owner, owner_required_message

    if not is_gateway_owner(
        platform=platform, external_id=external_id, session_key=session_key
    ):
        return owner_required_message()
    return None


@dataclass(frozen=True)
class CommandDef:
    name: str
    aliases: tuple[str, ...] = ()
    category: str = "其他"
    help_text: str = ""
    handler_ref: str = ""
    handler: Optional[CommandHandler] = field(default=None, repr=False, compare=False)
    visibility: str = "public"  # public | admin | hidden


_REGISTRY: dict[str, CommandDef] = {}
_ALIAS_MAP: dict[str, str] = {}


def register(cmd: CommandDef) -> None:
    _REGISTRY[cmd.name] = cmd
    for alias in cmd.aliases:
        _ALIAS_MAP[alias] = cmd.name


def lookup(name: str) -> CommandDef | None:
    canonical = _ALIAS_MAP.get(name, name)
    return _REGISTRY.get(canonical)


def dispatch(ctx: CommandContext) -> tuple[bool, str | None]:
    """Try to dispatch *ctx.cmd* through a registered handler.

    Returns ``(handled, response)``.  If no handler is registered for the
    command, returns ``(False, None)`` so the caller can fall through to
    legacy handling.
    """
    cmd_def = lookup(ctx.cmd)
    if cmd_def is None or cmd_def.handler is None:
        return False, None

    def _on_success() -> None:
        from butler.gateway.gateway_transcript import record_gateway_tool_action
        from butler.gateway.outbound_prefs import mark_slash_reply_single_bubble

        record_gateway_tool_action(
            ctx.session_key,
            tool_name=f"slash:{ctx.cmd}",
            args_preview=str(ctx.arg or "")[:400],
        )
        mark_slash_reply_single_bubble()

    from butler.gateway.command_registry_ops import dispatch_registered_command

    return dispatch_registered_command(
        cmd=ctx.cmd,
        handler=cmd_def.handler,
        ctx=ctx,
        on_success=_on_success,
    )


def all_commands(*, visibility: str | None = None) -> list[CommandDef]:
    cmds = list(_REGISTRY.values())
    if visibility:
        cmds = [c for c in cmds if c.visibility == visibility]
    return sorted(cmds, key=lambda c: (c.category, c.name))


def categories() -> dict[str, list[CommandDef]]:
    result: dict[str, list[CommandDef]] = {}
    for cmd in _REGISTRY.values():
        if cmd.visibility == "hidden":
            continue
        result.setdefault(cmd.category, []).append(cmd)
    return {k: sorted(v, key=lambda c: c.name) for k, v in sorted(result.items())}


def format_registry_help(topic: str = "") -> str:
    """Generate help text from the registry."""
    if topic:
        cmd = lookup(f"/{topic}") or lookup(topic)
        if cmd:
            aliases = ", ".join(cmd.aliases) if cmd.aliases else "无"
            return (
                f"命令: {cmd.name}\n"
                f"别名: {aliases}\n"
                f"分类: {cmd.category}\n"
                f"{cmd.help_text}"
            )
        return f"未找到命令: {topic}"

    cats = categories()
    lines = ["Butler 命令帮助\n"]
    for cat, cmds in cats.items():
        lines.append(f"[{cat}]")
        for c in cmds:
            alias_hint = f" ({', '.join(c.aliases[:2])})" if c.aliases else ""
            lines.append(f"  {c.name}{alias_hint} — {c.help_text.split(chr(10))[0]}")
        lines.append("")
    lines.append("查看详情: /帮助 <命令名>")
    return "\n".join(lines)


def _register_defaults() -> None:
    """Register all known Butler commands."""
    _defaults: list[CommandDef] = [
        CommandDef("/项目", ("/projects",), "项目管理", "列出所有项目"),
        CommandDef("/切换", ("/switch",), "项目管理", "切换当前项目"),
        CommandDef("/状态", ("/status",), "项目管理", "当前项目与管家状态"),
        CommandDef("/项目概况", (), "项目管理", "项目仪表盘（代码/任务/工具统计）"),
        CommandDef("/项目待办", (), "项目管理", "项目级待办事项"),
        CommandDef("/总览", ("/overview",), "项目管理", "项目总览与概要"),
        CommandDef("/会话", ("/session",), "对话控制", "查看/管理会话"),
        CommandDef("/新对话", ("/new",), "对话控制", "重置当前会话"),
        CommandDef("/steer", ("/指引",), "对话控制", "插入引导消息"),
        CommandDef("/queue", (), "对话控制", "入站队列模式"),
        CommandDef("/待办", ("/todo",), "对话控制", "查看/管理会话待办"),
        CommandDef("/循环", ("/loop",), "对话控制", "启动目标循环模式"),
        CommandDef("/停止循环", ("/stoploop",), "对话控制", "停止目标循环"),
        CommandDef("/模型", ("/model",), "模型", "查看/切换当前模型"),
        CommandDef("/预设", (), "模型", "列出 butler:// 预设"),
        CommandDef("/记忆待审", (), "记忆", "查看待审批记忆"),
        CommandDef("/批准记忆", (), "记忆", "批准待审记忆"),
        CommandDef("/拒绝记忆", (), "记忆", "拒绝待审记忆"),
        CommandDef("/记忆图谱", (), "记忆", "查看三元组关系图"),
        CommandDef("/记忆提炼", (), "记忆", "从 transcript 提炼记忆"),
        CommandDef("/记忆状态", (), "记忆", "查看记忆系统状态"),
        CommandDef("/权限", ("/perms",), "权限安全", "查看当前权限状态"),
        CommandDef("/批准一次", (), "权限安全", "放行一次被拦截的操作"),
        CommandDef("/始终允许", (), "权限安全", "永久放行某类操作"),
        CommandDef("/批准执行", (), "权限安全", "批准 terminal 命令"),
        CommandDef("/批准沙箱外", ("/approve-unsandboxed",), "权限安全", "批准 terminal 沙箱外执行"),
        CommandDef("/批准模式", (), "权限安全", "按模式批准（24h 有效）"),
        CommandDef("/确认安装", (), "权限安全", "确认 Skill/MCP 安装"),
        CommandDef("/确认", ("/approve",), "规划模式", "确认 workflow 步骤"),
        CommandDef("/取消", ("/cancel",), "规划模式", "取消 workflow 步骤"),
        CommandDef("/计划", ("/plan",), "规划模式", "进入规划模式"),
        CommandDef("/执行", ("/execute",), "规划模式", "退出规划，开始执行"),
        CommandDef("/git", (), "开发工具", "Git 状态摘要"),
        CommandDef("/测试", (), "开发工具", "运行项目测试"),
        CommandDef("/构建", (), "开发工具", "运行项目构建"),
        CommandDef("/开发状态", (), "开发工具", "开发环境概况"),
        CommandDef("/开发验收", (), "开发工具", "跑开发冒烟测试"),
        CommandDef("/诊断", ("/health",), "系统管理", "系统诊断"),
        CommandDef("/doctor", (), "系统管理", "安全审计报告"),
        CommandDef("/config", ("/配置",), "系统管理", "查看/修改系统配置"),
        CommandDef("/导出", ("/export",), "系统管理", "导出会话为 Markdown"),
        CommandDef("/回滚", (), "系统管理", "回滚 transcript"),
        CommandDef("/定时", ("/runtime",), "系统管理", "查看定时任务"),
        CommandDef("/工作流", ("/workflow",), "系统管理", "工作流管理"),
        CommandDef("/技能", ("/skill",), "系统管理", "Skill 搜索/安装/管理"),
        CommandDef("/mcp", (), "系统管理", "MCP 搜索/安装/管理"),
        CommandDef("/预算", ("/budget",), "系统管理", "设置本轮 token 预算"),
        CommandDef("/任务", ("/tasks",), "系统管理", "查看委派任务列表"),
        CommandDef("/评价", ("/evaluate",), "系统管理", "评估/评价当前结果"),
        CommandDef("/分叉", ("/fork",), "系统管理", "会话分叉"),
        CommandDef("/备忘", (), "日常生活", "查看备忘录"),
        CommandDef("/通讯录", (), "日常生活", "查看通讯录"),
        CommandDef("/记账", (), "日常生活", "查看记账概览"),
        CommandDef("/打卡", (), "日常生活", "查看习惯打卡"),
    ]
    for cmd in _defaults:
        register(cmd)


_register_defaults()

__all__ = [
    "CommandContext",
    "CommandDef",
    "CommandHandler",
    "all_commands",
    "categories",
    "dispatch",
    "format_registry_help",
    "lookup",
    "register",
]

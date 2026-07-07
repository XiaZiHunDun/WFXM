"""Slash-command dispatcher for the interactive chat loop.

Audit source: ``docs/reviews/project-deep-audit-2026-06-r1to8.md`` §R1-7

Extracted from ``butler/main.py`` as part of the R1-7 god-method split.
The pre-split ``_handle_slash_command`` was a 242-line if/elif chain
that handled every interactive slash command inline. Post-split:

* Each command is a small ``SlashCommand``-shaped handler in this
  module, organized by topic (``projects``, ``memory``, ``runtime``,
  ``gateway`` …) and registered in ``_SLASH_REGISTRY``.
* The dispatcher ``dispatch_slash_command`` is the only entry point
  consumed by the interactive loop; it returns the control token
  (``"quit"`` / ``"rebuild"`` / ``"rebuild_after_new"`` / ``"switch_project"``
  / ``"handled"`` / ``None``) that the loop uses to decide its next
  action.

The shape mirrors the ``CommandDef`` style used in
``butler.gateway.command_registry`` (R1-6's gateway-side equivalent)
but is intentionally separate: main.py's slash handler must return
control tokens, not user-facing strings, and the gateway handlers
have different return-value semantics. Tying the two registries
together would force one to compromise on its return contract.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Optional, cast

if TYPE_CHECKING:
    from butler.orchestrator import ButlerOrchestrator

from butler.execution_context import get_current_session_key
from butler.gateway.commands.memory_handlers import handle_memory_pending_command
from butler.model_resolve import handle_model_command
from butler.plan.mode import clear_plan_mode, format_plan_mode_status, set_plan_mode
from butler.session.lifecycle import sync_turn_memory as _lifecycle_sync_turn_memory
from butler.session.lifecycle import trigger_session_end as _lifecycle_trigger_session_end

from butler.session.keys import build_session_key
from butler.project.lead import lead_mode_switch_suffix
from butler.report.format import parse_detail_section
from butler.cli.slash_dispatch_ops import get_last_report_safe
from butler.report import format_detail
from butler.core.steer import steer
from butler.gateway.message_handler import ButlerMessageHandler
from butler.workflows.commands import handle_workflow_command
from butler.runtime.task_store import list_recent_tasks
from butler.session.new_session import handle_new_session_command

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

ReturnToken = str  # "quit" | "rebuild" | "rebuild_after_new" | "switch_project" | "handled"

# SlashHandler signature:
#   (orchestrator, console, arg, agent_loop)
#   -> Optional[str] | tuple[ReturnToken, str]
# The string is printed to the console. If the handler returns a
# tuple ``(token, response)``, the dispatcher uses ``token`` (overriding
# the command's default ``return_token``) and prints ``response``.
# This lets handlers signal "this is a success path" vs "this was a
# validation failure — just print and mark handled" without the
# dispatcher needing per-command branching.
SlashHandler = Callable[[Any, Any, str, Any], "str | tuple[str, str] | None"]


@dataclass(frozen=True)
class SlashCommand:
    """Registry entry — mirrors ``CommandDef`` style.

    The ``handler`` returns:
      * a string -> printed to the console; dispatcher returns ``return_token``;
      * a tuple ``(token, response)`` -> printed; dispatcher returns ``token``;
      * ``None`` -> nothing printed; dispatcher returns ``return_token``.

    Handlers that need to short-circuit the loop (e.g. ``/quit``) do so
    by choosing ``return_token="quit"``. Handlers that need to
    distinguish success from validation failure return a tuple.
    """

    name: str
    aliases: tuple[str, ...] = ()
    help_text: str = ""
    return_token: ReturnToken = "handled"
    handler: SlashHandler = field(default=lambda *_: None, repr=False)


_SLASH_REGISTRY: dict[str, SlashCommand] = {}
_ALIAS_MAP: dict[str, str] = {}


def register(cmd: SlashCommand) -> None:
    """Register a slash command (and its aliases)."""
    _SLASH_REGISTRY[cmd.name] = cmd
    for alias in cmd.aliases:
        _ALIAS_MAP[alias] = cmd.name


def lookup(name: str) -> SlashCommand | None:
    """Resolve a slash token to its SlashCommand (alias-aware)."""
    canonical = _ALIAS_MAP.get(name, name)
    return _SLASH_REGISTRY.get(canonical)


def all_slash_commands() -> list[SlashCommand]:
    """Return all registered slash commands (sorted by name)."""
    return sorted(_SLASH_REGISTRY.values(), key=lambda c: c.name)


# ---------------------------------------------------------------------------
# Helpers used by handlers
# ---------------------------------------------------------------------------


def _cli_session_key(orchestrator: Any) -> str:

    return str(
        build_session_key(
            platform="cli",
            chat_id=orchestrator.user_id,
            project=orchestrator.project_manager.current_project or "",
        )
    )


def _build_help(console: Any) -> str:
    """Render the static help text (read-only; no logic in the dispatcher)."""
    return (
        "[bold]Butler 命令:[/bold]\n"
        "  /projects       — 列出项目\n"
        "  /switch <名称>  — 切换项目\n"
        "  /model [角色] [provider/model] — 查看或切换模型\n"
        "  /new            — 新建对话（清空历史）\n"
        "  /status         — 当前状态\n"
        "  /health         — 运行时诊断（压缩、工具审计等）\n"
        "  /detail         — 上一次委派的详细报告\n"
        "  /workflow       — 列出或运行项目工作流 (DAG)\n"
        "  /steer <文本>   — 向运行中的 Agent 插入指引（不打断工具）\n"
        "  /记忆待审       — 列出项目 MEMORY Pending 队列\n"
        "  /记忆图谱       — 三元组展示（不参与检索）\n"
        "  /批准记忆 <序号|全部> — 批准待审记忆\n"
        "  /拒绝记忆 <序号|全部> — 拒绝待审记忆（清理 Pending 向量）\n"
        "  /quit           — 退出\n"
    )


# ---------------------------------------------------------------------------
# Handlers — one per command, each kept under 50 source lines
# ---------------------------------------------------------------------------


def _handle_help(_orch: Any, console: Any, _arg: str, _loop: Any) -> str:
    return _build_help(console)


def _handle_quit(*_a: Any, **_k: Any) -> None:
    return None  # dispatcher maps return_token="quit"


def _handle_projects(orch: Any, console: Any, _arg: str, _loop: Any) -> Optional[str]:
    projects = orch.project_manager.list_projects()
    current = orch.project_manager.current_project
    if not projects:
        return "[dim]暂无项目[/dim]"
    lines = []
    for p in sorted(projects, key=lambda x: x.name):
        mark = "*" if p.name == current else " "
        lines.append(f"  [{mark}] {p.name:20} ({p.type:8}) {p.description}")
    return "\n".join(lines)


def _handle_switch(orch: Any, console: Any, arg: str, _loop: Any) -> str | tuple[str, str] | None:
    """``/switch <name>``.

    Returns a ``(token, response)`` tuple so the dispatcher can
    distinguish the success path (rebuild loop for new project) from
    validation failures (just print and mark handled).
    """
    if not arg:
        return "handled", "[yellow]用法: /switch <项目名称>[/yellow]"
    if not orch.project_manager.switch_project(arg):
        return "handled", f"[red]未找到项目: {arg}[/red]"
    new = orch.project_manager.current_project
    note_line = _switch_lead_note(new or "")
    response = (
        f"[green]已切换到项目: {new}[/green] "
        "[dim]（该项目有独立对话历史）[/dim]"
        + (f"\n[dim]{note_line.strip()}[/dim]" if note_line else "")
    )
    return "switch_project", response


def _switch_lead_note(new_name: str) -> str:

    return str(lead_mode_switch_suffix(new_name or ""))


def _handle_model(orch: Any, console: Any, arg: str, _loop: Any) -> Optional[str]:
    """View/change current model. Returns a string; the loop
    rebuilds on model change by inspecting the orchestrator
    state (handled in main.py via the return token ``rebuild``)."""
    proj = orch.project_manager.get_current()
    proj_name = orch.project_manager.current_project or None
    reply, _reset = handle_model_command(
        arg,
        settings=orch._settings,
        project=proj,
        project_label=proj_name,
    )
    return str(reply)


def _handle_status(orch: Any, console: Any, _arg: str, _loop: Any) -> Optional[str]:
    settings = orch._settings
    current = orch.project_manager.current_project or "(无)"
    mc = orch._model_credentials("butler")
    cli_sk = _cli_session_key(orch)
    return (
        f"[bold]Butler 状态[/bold]\n"
        f"  管家: {settings.butler_name}\n"
        f"  当前项目: {current}\n"
        f"  模型: {mc.get('provider', '?')}/{mc.get('model', '?')}\n"
        f"  Butler Home: {settings.butler_home}\n"
        f"  {format_plan_mode_status(cli_sk).replace(chr(10), ' ')}\n"
    )


def _handle_detail(_orch: Any, console: Any, arg: str, _loop: Any) -> Optional[str]:

    report, err = get_last_report_safe()
    if err is not None:
        return f"[dim]{err}[/dim]"
    if not report:
        return "[dim]暂无可展示的详细报告[/dim]"

    return str(format_detail(report, section=parse_detail_section(arg)))


def _handle_steer(orch: Any, console: Any, arg: str, _loop: Any) -> Optional[str]:
    if not arg:
        return "[yellow]用法: /steer <指引文本>[/yellow]"

    if steer(arg, session_key="cli"):
        return "[dim]已加入指引，将在下一批工具结果后生效[/dim]"
    return None


# ---------------------------------------------------------------------------
# Memory, plan, runtime, health, workflow — thin shims that delegate to
# the existing gateway-side modules. These exist so the local registry
# has a single source of truth for "which commands does the CLI loop
# know about?".
# ---------------------------------------------------------------------------


def _handle_memory(orch: Any, _console: Any, arg: str, _loop: Any) -> Optional[str]:
    """Handle /记忆待审, /记忆图谱, /批准记忆, /拒绝记忆."""
    return handle_memory_pending_command(orch, "", arg) or None


def _handle_health(orch: Any, console: Any, _arg: str, agent_loop: Any) -> Optional[str]:

    handler = ButlerMessageHandler(channel="cli")
    handler._orchestrator = orch
    if agent_loop is not None:
        loop_diag = dict(getattr(agent_loop, "diagnostics", {}) or {})
        handler._health_by_session["cli"] = {
            "session_key": "cli",
            "platform": "cli",
            "hygiene_compressed": loop_diag.get("hygiene_compressed"),
            **{
                k: v
                for k, v in loop_diag.items()
                if str(k).startswith("context_")
            },
            "schema_recovered": loop_diag.get("schema_recovered"),
            "schema_keywords_stripped": loop_diag.get("schema_keywords_stripped"),
            "skill_context_injected": loop_diag.get("skill_context_injected"),
            "skill_matches": loop_diag.get("skill_matches"),
            "memory_context_injected": loop_diag.get("memory_context_injected"),
            "memory_prefetch_chars": loop_diag.get("memory_prefetch_chars"),
            "memory_context_chars": loop_diag.get("memory_context_chars"),
            "loop": loop_diag,
        }
    return str(handler._format_health_summary("cli"))


def _handle_workflow(orch: Any, _console: Any, arg: str, _loop: Any) -> Optional[str]:

    cli_sk = _cli_session_key(orch)
    return str(handle_workflow_command(orch, arg, session_key=cli_sk))


# ---------------------------------------------------------------------------
# Plan mode + /new + /tasks — short handlers that don't share the
# session-key building, kept separate for clarity.
# ---------------------------------------------------------------------------


def _handle_plan(orch: Any, _console: Any, arg: str, _loop: Any) -> Optional[str]:
    cli_sk = _cli_session_key(orch)
    arg_l = (arg or "").strip().lower()
    if arg_l in ("off", "exit", "执行", "退出", "关闭"):
        clear_plan_mode(cli_sk)
        return "[green]已退出规划模式[/green]"
    set_plan_mode(cli_sk, True)
    return str(format_plan_mode_status(cli_sk))


def _handle_exit_plan(orch: Any, _console: Any, _arg: str, _loop: Any) -> Optional[str]:
    clear_plan_mode(_cli_session_key(orch))
    return "[green]已退出规划模式[/green]"


def _handle_tasks(orch: Any, _console: Any, _arg: str, _loop: Any) -> Optional[str]:

    cli_sk = _cli_session_key(orch)
    rows = list_recent_tasks(cli_sk, limit=5)
    if not rows:
        return "[dim]暂无委派任务记录[/dim]"
    lines = []
    for row in rows:
        mark = (
            "✓"
            if row.get("success") is True
            else ("✗" if row.get("success") is False else "…")
        )
        lines.append(
            f"  {mark} {row.get('task_id')} [{row.get('status')}] "
            f"{(row.get('task_preview') or '')[:60]}"
        )
    return "\n".join(lines)


def _handle_new(orch: Any, _console: Any, _arg: str, agent_loop: Any) -> Optional[str]:
    """``/new`` returns the rebuild_after_new token via the registry entry."""

    cli_sk = _cli_session_key(orch)
    return str(handle_new_session_command(orch, cli_sk, agent_loop))


# ---------------------------------------------------------------------------
# Special ``/quit`` token — the dispatcher treats ``/quit``/``/exit``/``/q``
# separately because they bypass the registry and the loop checks for the
# bare token before any command lookup.
# ---------------------------------------------------------------------------

_QUIT_TOKENS = frozenset({"/quit", "/exit", "/q"})


# ---------------------------------------------------------------------------
# Local registry — keeps the dispatcher thin.
# ---------------------------------------------------------------------------

_LOCAL_COMMANDS: tuple[SlashCommand, ...] = (
    SlashCommand(
        name="/help",
        help_text="显示可用命令",
        return_token="handled",
        handler=_handle_help,
    ),
    SlashCommand(
        name="/projects",
        aliases=("/项目",),
        help_text="列出所有项目",
        return_token="handled",
        handler=_handle_projects,
    ),
    SlashCommand(
        name="/switch",
        aliases=("/切换",),
        help_text="切换当前项目",
        return_token="switch_project",
        handler=_handle_switch,
    ),
    SlashCommand(
        name="/model",
        aliases=("/模型",),
        help_text="查看/切换当前模型",
        return_token="handled",
        handler=_handle_model,
    ),
    SlashCommand(
        name="/new",
        aliases=("/新对话",),
        help_text="重置当前会话",
        return_token="rebuild_after_new",
        handler=_handle_new,
    ),
    SlashCommand(
        name="/status",
        aliases=("/状态",),
        help_text="当前项目与管家状态",
        return_token="handled",
        handler=_handle_status,
    ),
    SlashCommand(
        name="/plan",
        aliases=("/计划", "/规划"),
        help_text="进入/退出规划模式",
        return_token="handled",
        handler=_handle_plan,
    ),
    SlashCommand(
        name="/exit-plan",
        aliases=("/执行", "/退出规划"),
        help_text="退出规划模式",
        return_token="handled",
        handler=_handle_exit_plan,
    ),
    SlashCommand(
        name="/tasks",
        aliases=("/任务",),
        help_text="查看委派任务列表",
        return_token="handled",
        handler=_handle_tasks,
    ),
    SlashCommand(
        name="/health",
        aliases=("/诊断",),
        help_text="运行时诊断（压缩、工具审计等）",
        return_token="handled",
        handler=_handle_health,
    ),
    SlashCommand(
        name="/steer",
        aliases=("/指引",),
        help_text="向运行中的 Agent 插入指引（不打断工具）",
        return_token="handled",
        handler=_handle_steer,
    ),
    SlashCommand(
        name="/detail",
        help_text="上一次委派的详细报告",
        return_token="handled",
        handler=_handle_detail,
    ),
    SlashCommand(
        name="/workflow",
        aliases=("/工作流",),
        help_text="列出或运行项目工作流 (DAG)",
        return_token="handled",
        handler=_handle_workflow,
    ),
)


for _cmd in _LOCAL_COMMANDS:
    register(_cmd)


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


def dispatch_slash_command(
    cmd: str,
    orchestrator: Any,
    console: Any,
    *,
    agent_loop: Any | None = None,
) -> str | None:
    """Dispatch a single slash command. See module docstring for token list."""
    parts = cmd.strip().split(maxsplit=1)
    command = parts[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""

    if command in _QUIT_TOKENS:
        return "quit"

    # Memory commands live in gateway-side helper; they accept /记忆*
    # /批准记忆 /拒绝记忆 etc. and return the response text.
    mem_resp = handle_memory_pending_command(orchestrator, command, arg)
    if mem_resp is not None:
        console.print(mem_resp)
        return "handled"

    cmd_def = lookup(command)
    if cmd_def is None:
        return None

    # Special handling for /model — rebuild if reset_loop signal.
    if command in ("/model", "/模型"):
        response, reset_loop = _resolve_model_response(orchestrator, arg)
        if reset_loop:
            console.print(f"[green]{response}[/green]")
            return "rebuild"
        console.print(response)
        return "handled"

    raw = cmd_def.handler(orchestrator, console, arg, agent_loop)
    if isinstance(raw, tuple):
        token, response = raw
        if response:
            console.print(response)
        return token
    if raw:
        console.print(raw)
    return cmd_def.return_token


def _resolve_model_response(orchestrator: Any, arg: str) -> tuple[str, bool]:
    """``/model`` returns ``(reply, reset_loop)`` from the underlying
    resolver. Pulled out so the dispatcher stays under 50 lines."""
    proj = orchestrator.project_manager.get_current()
    proj_name = orchestrator.project_manager.current_project or None
    return cast(
        tuple[str, bool],
        handle_model_command(
            arg,
            settings=orchestrator._settings,
            project=proj,
            project_label=proj_name,
        ),
    )


# ---------------------------------------------------------------------------
# Session helpers — moved out of main.py for the same R1-7 reason.
# ---------------------------------------------------------------------------


def sync_turn_memory(
    orchestrator: "ButlerOrchestrator",
    user_msg: str,
    assistant_msg: str,
    *,
    interrupted: bool = False,
    status: Any = None,
) -> None:
    """Sync conversation turn to butler memory for experience tracking."""
    _lifecycle_sync_turn_memory(
        orchestrator,
        user_msg,
        assistant_msg,
        interrupted=interrupted,
        status=status,
        session_id=get_current_session_key(),
    )


def trigger_session_end(
    orchestrator: "ButlerOrchestrator",
    agent_loop: Any,
) -> None:
    """Trigger post-session processing (memory/skill extraction)."""
    _lifecycle_trigger_session_end(orchestrator, agent_loop, reason="shutdown")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

# Back-compat alias — the pre-R1-7 name was ``_handle_slash_command``.
# New code should use ``dispatch_slash_command``.
_handle_slash_command = dispatch_slash_command
_sync_memory = sync_turn_memory
_trigger_session_end = trigger_session_end

__all__ = [
    "SlashCommand",
    "_handle_slash_command",
    "_sync_memory",
    "_trigger_session_end",
    "all_slash_commands",
    "dispatch_slash_command",
    "lookup",
    "register",
    "sync_turn_memory",
    "trigger_session_end",
]

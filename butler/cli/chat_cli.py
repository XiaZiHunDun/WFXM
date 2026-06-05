"""CLI: ``butler chat`` (interactive) + ``butler exec`` (single-shot).

Audit source: ``docs/reviews/project-deep-audit-2026-06-r1to8.md`` §R1-7

Extracted from ``butler/main.py`` as part of the R1-7 god-method split.
The pre-split ``_run_interactive_chat`` (205L) was a monolith of the
entire interactive loop; the pre-split ``_cmd_exec`` (51L) needed to
drop below the 50-line cap.

Post-split shape (R1-6 phase-function pattern):

* ``_run_interactive_chat`` is a thin orchestrator that calls the
  ``_phase_*`` helpers in order.
* Each ``_phase_*`` helper is kept under 50 source lines.
* ``_cmd_exec`` is a thin wrapper around ``_phase_run_single_turn``.

This mirrors the R1-6 ``message_pipelines`` / ``locked_phases``
pattern: extract each step into its own function, keep the public
function as a linear list of ``phase_*(...)`` calls.
"""

from __future__ import annotations

import argparse
import sys
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from butler.orchestrator import ButlerOrchestrator


# ---------------------------------------------------------------------------
# Public entry points — argparse handlers.
# ---------------------------------------------------------------------------


def register_chat_parser(sub: argparse._SubParsersAction) -> None:
    """Register ``chat`` (interactive) and ``exec`` (single-shot) parsers."""
    from butler import main as _butler_main

    sub.add_parser("chat", help="交互式对话").set_defaults(func=_butler_main._cmd_chat)
    ex = sub.add_parser("exec", help="单次消息执行")
    ex.add_argument("message")
    ex.set_defaults(func=_butler_main._cmd_exec)


def _cmd_chat(_ns: argparse.Namespace) -> int:
    from butler.orchestrator import ButlerOrchestrator

    orch = ButlerOrchestrator(user_id="owner", channel="cli")
    return _run_interactive_chat(orch)


def _cmd_exec(ns: argparse.Namespace) -> int:
    """Single-shot message execution — thin wrapper around the turn
    pipeline so the function stays under the 50-line cap."""
    from butler.orchestrator import ButlerOrchestrator

    console = _stderr_console()
    orch = ButlerOrchestrator(user_id="owner", channel="cli")

    if not _phase_apply_user_prompt_hooks(orch, ns.message.strip(), console):
        return 1

    _phase_render_user_message(console, ns.message)
    ui, stream = _phase_build_exec_ui(console)
    agent_loop = _phase_create_exec_loop(orch, ui, stream)

    try:
        result = _phase_run_single_turn(orch, agent_loop, ns.message, ui, stream)
        return 0 if result.status.value == "completed" else 1
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


# ---------------------------------------------------------------------------
# Interactive chat — thin orchestrator.
# ---------------------------------------------------------------------------


def _run_interactive_chat(orchestrator: "ButlerOrchestrator") -> int:
    """Interactive chat loop using Butler's own AgentLoop.

    R1-7 refactored: this function is now a thin orchestrator. Each
    step of the loop lives in a ``_phase_*`` helper below.
    """
    from butler.cli.slash_commands import build_slash_completer

    console, session, settings = _phase_setup_interactive_session(orchestrator)
    _phase_print_interactive_welcome(console, settings, orchestrator)

    # Local closure state
    from butler.cli.session_ui import ChatSessionUI

    ui = ChatSessionUI(console)
    loops_by_session: dict[str, Any] = {}
    agent_loop = _phase_get_or_create_loop(orchestrator, ui, loops_by_session)

    while True:
        user_input = _phase_prompt_user_input(session, console, orchestrator)
        if user_input is None:
            _phase_end_session(orchestrator, agent_loop)
            return 0

        # Skip empty / whitespace-only input (R1-7 parity with original).
        if not user_input:
            continue

        if user_input.startswith("/"):
            token, agent_loop = _phase_dispatch_slash(
                user_input, orchestrator, console, agent_loop, loops_by_session
            )
            if token == "quit":
                _phase_end_session(orchestrator, agent_loop)
                return 0
            if token:
                continue
            console.print(
                f"[yellow]未知命令: {user_input.split(maxsplit=1)[0]}[/yellow]"
            )
            console.print("[dim]输入 /help 查看可用命令[/dim]")
            continue

        if not _phase_check_user_prompt_hooks(orchestrator, user_input, console):
            continue
        agent_loop = _phase_run_interactive_turn(
            orchestrator, agent_loop, user_input, ui
        )

    return 0  # unreachable; loop returns above


# ---------------------------------------------------------------------------
# Phase helpers — each function is a small orchestrator.
# ---------------------------------------------------------------------------


def _stderr_console() -> Any:
    from rich.console import Console

    return Console(stderr=True)


def _phase_setup_interactive_session(orchestrator: Any) -> tuple[Any, Any, Any]:
    """Phase 1: console + PromptSession + history file."""
    from prompt_toolkit import PromptSession
    from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
    from prompt_toolkit.history import FileHistory

    from butler.cli.slash_commands import build_slash_completer

    console = _stderr_console()
    settings = orchestrator._settings
    history_file = settings.butler_home / "chat_history.txt"
    history_file.parent.mkdir(parents=True, exist_ok=True)
    session = PromptSession(
        history=FileHistory(str(history_file)),
        auto_suggest=AutoSuggestFromHistory(),
        completer=build_slash_completer(),
    )
    return console, session, settings


def _phase_print_interactive_welcome(console: Any, settings: Any, orchestrator: Any) -> None:
    """Phase 2: print the welcome panel with project + model info."""
    from rich.panel import Panel

    current_project = orchestrator.project_manager.current_project or "(无)"
    mc = orchestrator._model_credentials("butler")
    model_display = f"{mc.get('provider', '?')}/{mc.get('model', '?')}"
    console.print(
        Panel(
            f"[bold]Butler AI 管家[/bold] — {settings.butler_name}\n"
            f"项目: [cyan]{current_project}[/cyan] | 模型: [green]{model_display}[/green]\n"
            f"输入 /help 查看命令，Ctrl+C 中断当前轮，Ctrl+D 退出",
            title="Butler v4",
            border_style="blue",
        )
    )


def _phase_prompt_user_input(
    session: Any, console: Any, orchestrator: Any
) -> str | None:
    """Phase 3: read one user input. Returns ``None`` on EOF/KeyboardInterrupt."""
    from prompt_toolkit.patch_stdout import patch_stdout

    try:
        project = orchestrator.project_manager.current_project or "Butler"
        prompt_prefix = f"[{project}] > "
        with patch_stdout():
            return session.prompt(prompt_prefix).strip()
    except (EOFError, KeyboardInterrupt):
        console.print("\n[dim]再见！[/dim]")
        return None


def _phase_dispatch_slash(
    user_input: str,
    orchestrator: Any,
    console: Any,
    agent_loop: Any,
    loops_by_session: dict[str, Any],
) -> tuple[str | None, Any]:
    """Phase 4: route a slash command. Returns (token, new_agent_loop)."""
    from butler.cli.slash_dispatch import dispatch_slash_command

    handled = dispatch_slash_command(
        user_input, orchestrator, console, agent_loop=agent_loop
    )
    if handled == "rebuild_after_new":
        agent_loop = _phase_rebuild_loop(orchestrator, agent_loop, loops_by_session, skip_session_end=True)
    elif handled == "rebuild":
        agent_loop = _phase_rebuild_loop(orchestrator, agent_loop, loops_by_session)
    elif handled == "switch_project":
        agent_loop = _phase_get_or_create_loop(orchestrator, console, loops_by_session, ui=None)  # type: ignore[arg-type]
    return handled, agent_loop


def _phase_check_user_prompt_hooks(orchestrator: Any, user_input: str, console: Any) -> bool:
    """Phase 5: run UserPromptSubmit hooks. Returns True if the prompt
    should proceed; False if a hook blocked it."""
    from butler.hooks.runner import run_user_prompt_submit_hooks
    from butler.session.keys import build_session_key

    cli_sk = build_session_key(
        platform="cli",
        chat_id=orchestrator.user_id,
        project=orchestrator.project_manager.current_project or "",
    )
    prompt_hooks = run_user_prompt_submit_hooks(
        user_input.strip(), session_key=cli_sk, platform="cli"
    )
    if prompt_hooks.blocked:
        console.print(f"[yellow]{prompt_hooks.block_message}[/yellow]")
        return False
    if prompt_hooks.prevent_continuation:
        console.print(
            f"[yellow]{prompt_hooks.stop_message or '已停止（UserPromptSubmit hook）'}[/yellow]"
        )
        return False
    return True


def _phase_augment_prompt(orchestrator: Any, user_input: str) -> str:
    """Phase 6: apply pre-LLM context (skill injection + hook context)."""
    from butler.gateway.hooks import apply_pre_llm_context

    return apply_pre_llm_context(
        orchestrator.inject_skill_context(user_input),
        orchestrator=orchestrator,
    )


def _phase_run_interactive_turn(
    orchestrator: Any,
    agent_loop: Any,
    user_input: str,
    ui: Any,
) -> Any:
    """Phase 7: run one turn in the interactive loop. Returns the
    (possibly rebuilt) agent loop. Splits the body across
    ``_phase_execute_turn`` and ``_phase_finalize_turn`` to stay
    under the 50-line cap."""
    from butler.cli.stream import StreamRenderer

    settings = orchestrator._settings
    stream = StreamRenderer(_stderr_console(), title=settings.butler_name or "Butler")
    agent_loop.callbacks = ui.build_callbacks(stream)
    augmented = _phase_augment_prompt(orchestrator, user_input)

    try:
        return _phase_execute_turn(orchestrator, agent_loop, user_input, augmented, ui, stream)
    except KeyboardInterrupt:
        return _phase_handle_keyboard_interrupt(agent_loop, ui, stream)
    except Exception as exc:
        return _phase_handle_turn_error(agent_loop, exc)


def _phase_execute_turn(
    orchestrator: Any,
    agent_loop: Any,
    user_input: str,
    augmented: str,
    ui: Any,
    stream: Any,
) -> Any:
    """Execute one turn + finalize (memory sync, prefetch)."""
    from butler import main as _butler_main
    from butler.core.agent_loop import LoopStatus
    from butler.execution_context import use_execution_context
    from butler.session.keys import build_session_key
    from butler.session.lifecycle import attach_turn_memory_prefetch, queue_prefetch_after_turn

    cli_sk = build_session_key(
        platform="cli",
        chat_id=orchestrator.user_id,
        project=orchestrator.project_manager.current_project or "",
    )
    attach_turn_memory_prefetch(agent_loop, orchestrator, user_input, role="butler")
    with use_execution_context(orchestrator, session_key=cli_sk):
        result = agent_loop.run(augmented)
    ui.finish_turn(result, stream)
    with use_execution_context(orchestrator, session_key=cli_sk):
        _butler_main._sync_memory(
            orchestrator,
            user_input,
            result.final_response or "",
            interrupted=result.status == LoopStatus.INTERRUPTED,
            status=result.status,
        )
        queue_prefetch_after_turn(
            orchestrator,
            user_input,
            role="butler",
            session_id=cli_sk,
        )
    return agent_loop


def _phase_handle_keyboard_interrupt(agent_loop: Any, ui: Any, stream: Any) -> Any:
    from butler.core.agent_loop import LoopResult, LoopStatus

    _stderr_console().print("\n[dim]已中断[/dim]")
    agent_loop.interrupt()
    if stream is not None:
        ui.finish_turn(
            LoopResult(
                status=LoopStatus.INTERRUPTED,
                final_response=stream.text.strip() or None,
            ),
            stream,
        )
    return agent_loop


def _phase_handle_turn_error(agent_loop: Any, exc: BaseException) -> Any:
    import logging

    _stderr_console().print(f"\n[bold red]错误:[/bold red] {exc}\n")
    logging.getLogger(__name__).exception("Agent loop error")
    return agent_loop


# ---------------------------------------------------------------------------
# Loop factory / session-end helpers.
# ---------------------------------------------------------------------------


def _phase_get_or_create_loop(
    orchestrator: Any,
    _ui_or_console: Any,
    loops_by_session: dict[str, Any],
    *,
    ui: Any = None,
) -> Any:
    """Create or fetch the cached AgentLoop for the current session key."""
    from butler.project.lead import gateway_loop_role
    from butler.session.keys import build_session_key
    from butler.tools.project_tools import get_current_project_tools
    from butler.tools.registry import dispatch_tool

    cli_sk = build_session_key(
        platform="cli",
        chat_id=orchestrator.user_id,
        project=orchestrator.project_manager.current_project or "",
    )
    role = gateway_loop_role(orchestrator.project_manager.current_project or "")
    cached = loops_by_session.get(cli_sk)
    if cached is not None:
        return cached
    if ui is None:
        # Caller didn't pass a UI (e.g. dispatch_slash switch_project);
        # build a stub ChatSessionUI to satisfy the loop factory.
        from butler.cli.session_ui import ChatSessionUI

        ui = ChatSessionUI(_stderr_console())
    stream = ui.begin_turn()
    callbacks = ui.build_callbacks(stream)
    agent_loop = orchestrator.create_agent_loop(
        role=role,
        tools=get_current_project_tools(role=role),
        tool_dispatcher=dispatch_tool,
        callbacks=callbacks,
        session_key=cli_sk,
    )
    loops_by_session[cli_sk] = agent_loop
    return agent_loop


def _phase_rebuild_loop(
    orchestrator: Any,
    old_loop: Any,
    loops_by_session: dict[str, Any],
    *,
    skip_session_end: bool = False,
) -> Any:
    """Pop the cached loop (running session-end if needed) and create a fresh one."""
    from butler import main as _butler_main
    from butler.session.keys import build_session_key
    from butler.cli.session_ui import ChatSessionUI

    cli_sk = build_session_key(
        platform="cli",
        chat_id=orchestrator.user_id,
        project=orchestrator.project_manager.current_project or "",
    )
    old = loops_by_session.pop(cli_sk, None)
    if old is not None and not skip_session_end:
        _butler_main._trigger_session_end(orchestrator, old)
    ui = ChatSessionUI(_stderr_console())
    stream = ui.begin_turn()
    from butler.project.lead import gateway_loop_role
    from butler.tools.project_tools import get_current_project_tools
    from butler.tools.registry import dispatch_tool

    role = gateway_loop_role(orchestrator.project_manager.current_project or "")
    new_loop = orchestrator.create_agent_loop(
        role=role,
        tools=get_current_project_tools(role=role),
        tool_dispatcher=dispatch_tool,
        callbacks=ui.build_callbacks(stream),
        session_key=cli_sk,
    )
    loops_by_session[cli_sk] = new_loop
    return new_loop


def _phase_end_session(orchestrator: Any, agent_loop: Any) -> None:
    # Late import: tests patch ``butler.main._trigger_session_end`` and
    # expect the loop to call the mock. Resolving at call time keeps
    # the patch path live.
    from butler import main as _butler_main

    _butler_main._trigger_session_end(orchestrator, agent_loop)


# ---------------------------------------------------------------------------
# Single-turn pipeline for ``_cmd_exec`` (refactored to drop under 50L).
# ---------------------------------------------------------------------------


def _phase_apply_user_prompt_hooks(orch: Any, message: str, console: Any) -> bool:
    from butler.hooks.runner import run_user_prompt_submit_hooks

    prompt_hooks = run_user_prompt_submit_hooks(message, session_key="cli", platform="cli")
    if prompt_hooks.blocked:
        console.print(prompt_hooks.block_message or "[yellow]已阻止[/yellow]")
        return False
    return True


def _phase_render_user_message(console: Any, message: str) -> None:
    from butler.cli.session_ui import ChatSessionUI

    ui = ChatSessionUI(console, stream_title="exec")
    ui.print_user_message(message)


def _phase_build_exec_ui(console: Any) -> tuple[Any, Any]:
    from butler.cli.session_ui import ChatSessionUI
    from butler.cli.stream import StreamRenderer

    ui = ChatSessionUI(console, stream_title="exec")
    stream = ui.begin_turn()
    return ui, stream


def _phase_create_exec_loop(orch: Any, ui: Any, stream: Any) -> Any:
    from butler.tools.project_tools import get_current_project_tools
    from butler.tools.registry import dispatch_tool

    return orch.create_agent_loop(
        role="butler",
        tools=get_current_project_tools(role="butler"),
        tool_dispatcher=dispatch_tool,
        callbacks=ui.build_callbacks(stream),
    )


def _phase_run_single_turn(orch: Any, agent_loop: Any, message: str, ui: Any, stream: Any) -> Any:
    """Run a single turn for ``butler exec``. Mirrors the interactive
    turn pipeline but with deterministic hooks (no slash dispatch)."""
    from butler import main as _butler_main
    from butler.core.agent_loop import LoopStatus
    from butler.execution_context import use_execution_context
    from butler.session.lifecycle import attach_turn_memory_prefetch

    augmented = _phase_augment_prompt_exec(orch, message)
    attach_turn_memory_prefetch(agent_loop, orch, message, role="butler")
    with use_execution_context(orch, session_key="cli"):
        result = agent_loop.run(augmented)
    ui.finish_turn(result, stream)
    with use_execution_context(orch, session_key="cli"):
        _butler_main._sync_memory(
            orch,
            message,
            result.final_response or "",
            interrupted=result.status == LoopStatus.INTERRUPTED,
            status=result.status,
        )
    return result


def _phase_augment_prompt_exec(orch: Any, message: str) -> str:
    from butler.gateway.hooks import apply_pre_llm_context

    return apply_pre_llm_context(
        orch.inject_skill_context(message),
        orchestrator=orch,
    )

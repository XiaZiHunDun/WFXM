#!/usr/bin/env python3
"""Butler CLI — self-contained Agent Loop architecture.

Butler controls its own Agent Loop, using the Transport layer for
LLM calls. No dependency on Hermes AIAgent.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Any, Sequence

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _run_interactive_chat(orchestrator: "ButlerOrchestrator") -> int:
    """Interactive chat loop using Butler's own AgentLoop."""
    from prompt_toolkit import PromptSession
    from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
    from prompt_toolkit.history import FileHistory
    from prompt_toolkit.patch_stdout import patch_stdout
    from rich.console import Console
    from rich.panel import Panel

    from butler.cli.session_ui import ChatSessionUI
    from butler.core.agent_loop import LoopStatus
    from butler.tools.registry import dispatch_tool, get_tool_definitions

    console = Console()
    settings = orchestrator._settings
    history_file = settings.butler_home / "chat_history.txt"
    history_file.parent.mkdir(parents=True, exist_ok=True)
    session = PromptSession(
        history=FileHistory(str(history_file)),
        auto_suggest=AutoSuggestFromHistory(),
    )

    current_project = orchestrator.project_manager.current_project or "(无)"
    mc = orchestrator._model_credentials("butler")
    model_display = f"{mc.get('provider', '?')}/{mc.get('model', '?')}"

    console.print(Panel(
        f"[bold]Butler AI 管家[/bold] — {settings.butler_name}\n"
        f"项目: [cyan]{current_project}[/cyan] | 模型: [green]{model_display}[/green]\n"
        f"输入 /help 查看命令，Ctrl+C 中断当前轮，Ctrl+D 退出",
        title="Butler v4",
        border_style="blue",
    ))

    tools = get_tool_definitions()
    ui = ChatSessionUI(console)
    agent_loop = None

    def _rebuild_loop():
        nonlocal agent_loop
        stream = ui.begin_turn()
        callbacks = ui.build_callbacks(stream)

        agent_loop = orchestrator.create_agent_loop(
            role="butler",
            tools=tools,
            tool_dispatcher=dispatch_tool,
            callbacks=callbacks,
        )
        return agent_loop

    agent_loop = _rebuild_loop()

    while True:
        try:
            project = orchestrator.project_manager.current_project or "Butler"
            prompt_prefix = f"[{project}] > "
            with patch_stdout():
                user_input = session.prompt(prompt_prefix).strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]再见！[/dim]")
            _trigger_session_end(orchestrator, agent_loop)
            return 0

        if not user_input:
            continue

        if user_input.startswith("/"):
            handled = _handle_slash_command(user_input, orchestrator, console)
            if handled == "quit":
                _trigger_session_end(orchestrator, agent_loop)
                return 0
            if handled == "rebuild":
                _trigger_session_end(orchestrator, agent_loop)
                agent_loop = _rebuild_loop()
            if handled:
                continue

        augmented = orchestrator.inject_skill_context(user_input)
        stream = ui.begin_turn()
        agent_loop.callbacks = ui.build_callbacks(stream)

        try:
            with patch_stdout():
                from butler.execution_context import use_execution_context
                from butler.session_lifecycle import attach_turn_memory_prefetch

                attach_turn_memory_prefetch(agent_loop, orchestrator, user_input, role="butler")
                with use_execution_context(orchestrator, session_key="cli"):
                    result = agent_loop.run(augmented)
            ui.finish_turn(result, stream)

            with use_execution_context(orchestrator, session_key="cli"):
                _sync_memory(
                    orchestrator,
                    user_input,
                    result.final_response or "",
                    interrupted=result.status == LoopStatus.INTERRUPTED,
                    status=result.status,
                )

        except KeyboardInterrupt:
            console.print("\n[dim]已中断[/dim]")
            agent_loop.interrupt()
            from butler.core.agent_loop import LoopResult
            ui.finish_turn(
                LoopResult(
                    status=LoopStatus.INTERRUPTED,
                    final_response=stream.text.strip() or None,
                ),
                stream,
            )

        except Exception as exc:
            console.print(f"\n[bold red]错误:[/bold red] {exc}\n")
            logger.exception("Agent loop error")

    return 0


def _sync_memory(
    orchestrator: "ButlerOrchestrator",
    user_msg: str,
    assistant_msg: str,
    *,
    interrupted: bool = False,
    status: Any = None,
) -> None:
    """Sync conversation turn to butler memory for experience tracking."""
    from butler.execution_context import get_current_session_key
    from butler.session_lifecycle import sync_turn_memory
    sync_turn_memory(
        orchestrator,
        user_msg,
        assistant_msg,
        interrupted=interrupted,
        status=status,
        session_id=get_current_session_key(),
    )


def _trigger_session_end(
    orchestrator: "ButlerOrchestrator",
    agent_loop: Any,
) -> None:
    """Trigger post-session processing (memory/skill extraction)."""
    from butler.session_lifecycle import trigger_session_end
    trigger_session_end(orchestrator, agent_loop)


def _handle_slash_command(
    cmd: str,
    orchestrator: "ButlerOrchestrator",
    console: Any,
) -> str | None:
    parts = cmd.strip().split(maxsplit=1)
    command = parts[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""

    if command in ("/quit", "/exit", "/q"):
        return "quit"

    if command == "/help":
        console.print(
            "[bold]Butler 命令:[/bold]\n"
            "  /projects       — 列出项目\n"
            "  /switch <名称>  — 切换项目\n"
            "  /model [角色] [provider/model] — 查看或切换模型\n"
            "  /new            — 新建对话（清空历史）\n"
            "  /status         — 当前状态\n"
            "  /detail         — 上一次委派的详细报告\n"
            "  /steer <文本>   — 向运行中的 Agent 插入指引（不打断工具）\n"
            "  /quit           — 退出\n"
        )
        return "handled"

    if command == "/projects":
        projects = orchestrator.project_manager.list_projects()
        current = orchestrator.project_manager.current_project
        if not projects:
            console.print("[dim]暂无项目[/dim]")
        else:
            for p in sorted(projects, key=lambda x: x.name):
                mark = "*" if p.name == current else " "
                console.print(f"  [{mark}] {p.name:20} ({p.type:8}) {p.description}")
        return "handled"

    if command == "/switch":
        if not arg:
            console.print("[yellow]用法: /switch <项目名称>[/yellow]")
            return "handled"
        ok = orchestrator.project_manager.switch_project(arg)
        if ok:
            new = orchestrator.project_manager.current_project
            console.print(f"[green]已切换到项目: {new}[/green]")
            return "rebuild"
        else:
            console.print(f"[red]未找到项目: {arg}[/red]")
        return "handled"

    if command == "/model":
        if not arg:
            from butler.config import get_model_config
            for role in ("butler", "dev_agent", "content_agent", "review_agent"):
                mc = get_model_config(role)
                console.print(f"  {role:16} → {mc.provider or '-'}/{mc.model or '-'}")
            return "handled"
        role_and_model = arg.split(maxsplit=1)
        if len(role_and_model) == 2:
            from butler.config import ModelConfig
            role_name, model_spec = role_and_model
            provider_model = model_spec.split("/", 1)
            if len(provider_model) == 2:
                cfg = ModelConfig(provider=provider_model[0], model=provider_model[1])
            else:
                cfg = ModelConfig(model=model_spec)
            orchestrator._settings.set_runtime_model_override(role_name, cfg)
            console.print(f"[green]已设置 {role_name} → {model_spec}[/green]")
            return "rebuild"
        console.print("[yellow]用法: /model <角色> <provider/model>[/yellow]")
        return "handled"

    if command == "/new":
        console.print("[dim]已清空对话历史[/dim]")
        return "rebuild"

    if command == "/status":
        settings = orchestrator._settings
        current = orchestrator.project_manager.current_project or "(无)"
        mc = orchestrator._model_credentials("butler")
        console.print(
            f"[bold]Butler 状态[/bold]\n"
            f"  管家: {settings.butler_name}\n"
            f"  当前项目: {current}\n"
            f"  模型: {mc.get('provider', '?')}/{mc.get('model', '?')}\n"
            f"  Butler Home: {settings.butler_home}\n"
        )
        return "handled"

    if command == "/steer":
        if not arg:
            console.print("[yellow]用法: /steer <指引文本>[/yellow]")
            return "handled"
        from butler.core.steer import steer
        if steer(arg):
            console.print("[dim]已加入指引，将在下一批工具结果后生效[/dim]")
        return "handled"

    if command == "/detail":
        from butler.report import get_last_report
        try:
            report = get_last_report()
            if report:
                from butler.report import format_detail
                console.print(format_detail(report))
            else:
                console.print("[dim]暂无可展示的详细报告[/dim]")
        except Exception:
            console.print("[dim]报告系统不可用[/dim]")
        return "handled"

    return None


def _cmd_chat(_ns: argparse.Namespace) -> int:
    from butler.orchestrator import ButlerOrchestrator
    orch = ButlerOrchestrator(user_id="owner", channel="cli")
    return _run_interactive_chat(orch)


def _cmd_exec(ns: argparse.Namespace) -> int:
    from butler.cli.session_ui import ChatSessionUI
    from butler.core.agent_loop import LoopStatus
    from butler.orchestrator import ButlerOrchestrator
    from butler.tools.registry import dispatch_tool, get_tool_definitions
    from rich.console import Console

    console = Console()
    orch = ButlerOrchestrator(user_id="owner", channel="cli")
    augmented = orch.inject_skill_context(ns.message)
    ui = ChatSessionUI(console, stream_title="exec")
    stream = ui.begin_turn()

    agent_loop = orch.create_agent_loop(
        role="butler",
        tools=get_tool_definitions(),
        tool_dispatcher=dispatch_tool,
        callbacks=ui.build_callbacks(stream),
    )

    try:
        from butler.session_lifecycle import attach_turn_memory_prefetch

        from butler.execution_context import use_execution_context

        attach_turn_memory_prefetch(agent_loop, orch, ns.message, role="butler")
        with use_execution_context(orch, session_key="cli"):
            result = agent_loop.run(augmented)
        ui.finish_turn(result, stream)
        with use_execution_context(orch, session_key="cli"):
            _sync_memory(
                orch,
                ns.message,
                result.final_response or "",
                interrupted=result.status == LoopStatus.INTERRUPTED,
                status=result.status,
            )
        return 0 if result.status.value == "completed" else 1
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def _cmd_projects(_ns: argparse.Namespace) -> int:
    from butler.project_manager import get_project_manager
    manager = get_project_manager()
    projects = sorted(manager.list_projects(), key=lambda p: p.name)
    if not projects:
        print("No projects found.", file=sys.stderr)
        return 0
    current = manager.current_project
    for proj in projects:
        mark = "*" if proj.name == current else " "
        print(f"[{mark}] {proj.name:20} ({proj.type:8})  {proj.workspace}")
    return 0


def _cmd_create(ns: argparse.Namespace) -> int:
    from butler.project_manager import get_project_manager
    mgr = get_project_manager()
    created = mgr.create_project(ns.name, ns.type_, ns.description)
    if created is None:
        print(f"Project {ns.name!r} already exists.", file=sys.stderr)
        return 1
    print(f"Created project {created.name} at {created.workspace}")
    return 0


def _cmd_gateway(ns: argparse.Namespace) -> int:
    """Start Hermes gateway with Butler plugin active.

    Gateway still uses Hermes subprocess since it manages platform
    adapters. Butler hooks into it via plugins.
    """
    os.environ["BUTLER_GATEWAY_ACTIVE"] = "1"
    os.environ.setdefault("HERMES_HOME", str(Path.home() / ".hermes"))

    try:
        from hermes_cli.plugins_cmd import _get_enabled_set, _save_enabled_set
        enabled = _get_enabled_set()
        for name in ("butler", "memory/butler"):
            enabled.add(name)
        _save_enabled_set(enabled)
    except Exception as exc:
        logger.warning("Could not auto-enable Butler plugins: %s", exc)

    import subprocess
    import shutil
    exe = shutil.which("hermes")
    if exe:
        argv = [exe, "gateway", "run"]
    else:
        argv = [sys.executable, str(_REPO_ROOT / "hermes_cli" / "main.py"), "gateway", "run"]
    if ns.platforms:
        argv.extend(["--platforms", ns.platforms])
    argv.extend(ns.hermes_remainder or [])
    result = subprocess.run(argv, cwd=str(_REPO_ROOT))
    return result.returncode


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="butler",
        description="Butler v4 — AI 管家系统（自建 Agent Loop 架构）",
    )
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("chat", help="交互式对话").set_defaults(func=_cmd_chat)
    sub.add_parser("projects", help="列出项目").set_defaults(func=_cmd_projects)

    cr = sub.add_parser("create", help="创建新项目")
    cr.add_argument("name")
    cr.add_argument("--type", dest="type_", default="software")
    cr.add_argument("--description", default="")
    cr.set_defaults(func=_cmd_create)

    ex = sub.add_parser("exec", help="单次消息执行")
    ex.add_argument("message")
    ex.set_defaults(func=_cmd_exec)

    gw = sub.add_parser("gateway", help="启动消息网关（通过 Hermes）")
    gw.add_argument("--platforms", default="")
    gw.add_argument("hermes_remainder", nargs=argparse.REMAINDER)
    gw.set_defaults(func=_cmd_gateway)

    return p


def main(argv: Sequence[str] | None = None) -> None:
    args = _build_parser().parse_args(argv)
    code = args.func(args)
    raise SystemExit(code)


if __name__ == "__main__":
    main()

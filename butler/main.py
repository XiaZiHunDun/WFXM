#!/usr/bin/env python3
"""Butler CLI — embedded Hermes AIAgent integration (Route C).

Instead of subprocess-calling ``hermes chat``, Butler directly constructs
and drives ``AIAgent`` from ``run_agent.py``, injecting Butler's system
prompt, model config, memory provider, and project context.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import Any, Sequence

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _ensure_hermes_env() -> None:
    """Set environment defaults that Hermes reads during import."""
    if not os.environ.get("HERMES_HOME"):
        os.environ["HERMES_HOME"] = str(Path.home() / ".hermes")


def _create_butler_agent(
    orchestrator: "ButlerOrchestrator",
    *,
    session_id: str | None = None,
    stream_delta_callback: Any = None,
    tool_start_callback: Any = None,
    tool_complete_callback: Any = None,
    quiet_mode: bool = False,
) -> "AIAgent":
    """Construct a Hermes AIAgent with Butler's configuration injected."""
    _ensure_hermes_env()
    from run_agent import AIAgent

    kwargs = orchestrator.get_agent_kwargs()

    agent = AIAgent(
        model=kwargs.get("model", ""),
        provider=kwargs.get("provider"),
        base_url=kwargs.get("base_url") or None,
        api_key=kwargs.get("api_key") or None,
        max_tokens=kwargs.get("max_tokens"),
        ephemeral_system_prompt=kwargs.get("ephemeral_system_prompt", ""),
        user_id=kwargs.get("user_id", "owner"),
        platform=kwargs.get("platform", "cli"),
        session_id=session_id,
        quiet_mode=quiet_mode,
        stream_delta_callback=stream_delta_callback,
        tool_start_callback=tool_start_callback,
        tool_complete_callback=tool_complete_callback,
    )
    return agent


def _create_project_agent(
    orchestrator: "ButlerOrchestrator",
    role: str,
    *,
    session_id: str | None = None,
    quiet_mode: bool = True,
) -> "AIAgent":
    """Construct a project-level Hermes AIAgent for delegation."""
    _ensure_hermes_env()
    from run_agent import AIAgent

    kwargs = orchestrator.get_project_agent_kwargs(role)
    proj = orchestrator.project_manager.get_current()
    workspace = str(proj.workspace) if proj else str(_REPO_ROOT)

    agent = AIAgent(
        model=kwargs.get("model", ""),
        provider=kwargs.get("provider"),
        base_url=kwargs.get("base_url") or None,
        api_key=kwargs.get("api_key") or None,
        max_tokens=kwargs.get("max_tokens"),
        ephemeral_system_prompt=kwargs.get("ephemeral_system_prompt", ""),
        user_id=kwargs.get("user_id", "owner"),
        platform=kwargs.get("platform", "cli"),
        session_id=session_id,
        quiet_mode=quiet_mode,
    )
    return agent


def _run_interactive_chat(orchestrator: "ButlerOrchestrator") -> int:
    """Interactive chat loop using Hermes AIAgent directly."""
    from rich.console import Console
    from rich.markdown import Markdown
    from rich.panel import Panel
    from prompt_toolkit import PromptSession
    from prompt_toolkit.history import FileHistory

    console = Console()
    settings = orchestrator._settings
    history_file = settings.butler_home / "chat_history.txt"
    history_file.parent.mkdir(parents=True, exist_ok=True)
    session = PromptSession(history=FileHistory(str(history_file)))

    current_project = orchestrator.project_manager.current_project or "(无)"
    mc = orchestrator._model_credentials("butler")
    model_display = f"{mc.get('provider', '?')}/{mc.get('model', '?')}"

    console.print(Panel(
        f"[bold]Butler AI 管家[/bold] — {settings.butler_name}\n"
        f"项目: [cyan]{current_project}[/cyan] | 模型: [green]{model_display}[/green]\n"
        f"输入 /help 查看命令，Ctrl+D 退出",
        title="Butler v3",
        border_style="blue",
    ))

    conversation_history: list[dict[str, Any]] = []
    agent: "AIAgent" | None = None

    def _rebuild_agent() -> "AIAgent":
        return _create_butler_agent(
            orchestrator,
            stream_delta_callback=lambda delta: console.print(delta, end="", highlight=False),
        )

    agent = _rebuild_agent()

    while True:
        try:
            prompt_prefix = f"[{orchestrator.project_manager.current_project or 'Butler'}] > "
            user_input = session.prompt(prompt_prefix).strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]再见！[/dim]")
            return 0

        if not user_input:
            continue

        if user_input.startswith("/"):
            handled = _handle_slash_command(
                user_input, orchestrator, console
            )
            if handled == "quit":
                return 0
            if handled == "rebuild":
                agent = _rebuild_agent()
                conversation_history.clear()
            if handled:
                continue

        augmented = orchestrator.inject_skill_context(user_input)

        try:
            result = agent.run_conversation(
                user_message=augmented,
                conversation_history=conversation_history,
            )
            response_text = result.get("response", "") if isinstance(result, dict) else str(result)
            if response_text:
                console.print()
                console.print(Markdown(response_text))
                console.print()

            if isinstance(result, dict) and "messages" in result:
                conversation_history = result["messages"]

        except Exception as exc:
            console.print(f"\n[bold red]错误:[/bold red] {exc}\n")
            logger.exception("Agent conversation error")

    return 0


def _handle_slash_command(
    cmd: str,
    orchestrator: "ButlerOrchestrator",
    console: Any,
) -> str | None:
    """Handle Butler slash commands. Returns action hint or None."""
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

    return None


def _cmd_chat(_ns: argparse.Namespace) -> int:
    from butler.orchestrator import ButlerOrchestrator
    orch = ButlerOrchestrator(user_id="owner", channel="cli")
    return _run_interactive_chat(orch)


def _cmd_exec(ns: argparse.Namespace) -> int:
    from butler.orchestrator import ButlerOrchestrator
    orch = ButlerOrchestrator(user_id="owner", channel="cli")
    agent = _create_butler_agent(orch, quiet_mode=True)
    augmented = orch.inject_skill_context(ns.message)
    try:
        result = agent.run_conversation(user_message=augmented)
        response = result.get("response", "") if isinstance(result, dict) else str(result)
        if response:
            print(response)
        return 0
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
    """Start Hermes gateway with Butler plugin active."""
    _ensure_hermes_env()
    os.environ["BUTLER_GATEWAY_ACTIVE"] = "1"
    from butler.config import get_butler_settings
    settings = get_butler_settings()
    os.environ.setdefault("HERMES_MEMORY_PROVIDER", "butler")

    import subprocess, shutil
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


def _cmd_wechat_setup(_ns: argparse.Namespace) -> int:
    _ensure_hermes_env()
    try:
        from hermes_cli.gateway import _setup_weixin
        _setup_weixin()
        return 0
    except ImportError as exc:
        print(f"WeChat setup requires gateway extras: {exc}", file=sys.stderr)
        return 1


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="butler",
        description="Butler v3 — AI 管家系统 (嵌入式 Hermes 集成)",
    )
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("chat", help="交互式对话（Butler 编排 + Hermes 引擎）").set_defaults(func=_cmd_chat)
    sub.add_parser("projects", help="列出项目").set_defaults(func=_cmd_projects)

    cr = sub.add_parser("create", help="创建新项目")
    cr.add_argument("name")
    cr.add_argument("--type", dest="type_", default="software")
    cr.add_argument("--description", default="")
    cr.set_defaults(func=_cmd_create)

    ex = sub.add_parser("exec", help="单次消息执行")
    ex.add_argument("message")
    ex.set_defaults(func=_cmd_exec)

    gw = sub.add_parser("gateway", help="启动 Hermes 消息网关")
    gw.add_argument("--platforms", default="")
    gw.add_argument("hermes_remainder", nargs=argparse.REMAINDER)
    gw.set_defaults(func=_cmd_gateway)

    sub.add_parser("wechat-setup", help="微信 QR 扫码登录").set_defaults(func=_cmd_wechat_setup)

    return p


def main(argv: Sequence[str] | None = None) -> None:
    args = _build_parser().parse_args(argv)
    code = args.func(args)
    raise SystemExit(code)


if __name__ == "__main__":
    main()

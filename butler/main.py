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
    from butler.cli.slash_commands import build_slash_completer, is_known_slash_command
    from butler.core.agent_loop import LoopStatus
    from butler.tools.registry import dispatch_tool
    from butler.tools.project_tools import get_current_project_tools

    # stderr: Rich output stays visible while prompt_toolkit patch_stdout() wraps prompts
    console = Console(stderr=True)
    settings = orchestrator._settings
    history_file = settings.butler_home / "chat_history.txt"
    history_file.parent.mkdir(parents=True, exist_ok=True)
    session = PromptSession(
        history=FileHistory(str(history_file)),
        auto_suggest=AutoSuggestFromHistory(),
        completer=build_slash_completer(),
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

    from butler.session_keys import build_session_key
    from butler.session_lifecycle import clear_session_boundary_memory

    ui = ChatSessionUI(console)
    loops_by_session: dict[str, Any] = {}
    agent_loop = None

    def _cli_session_key() -> str:
        return build_session_key(
            platform="cli",
            chat_id=orchestrator.user_id,
            project=orchestrator.project_manager.current_project or "",
        )

    def _cli_loop_role() -> str:
        from butler.project_lead import gateway_loop_role

        return gateway_loop_role(orchestrator.project_manager.current_project or "")

    def _create_loop():
        from butler.tools.project_tools import get_current_project_tools

        sk = _cli_session_key()
        role = _cli_loop_role()
        tools = get_current_project_tools(role=role)
        stream = ui.begin_turn()
        callbacks = ui.build_callbacks(stream)
        return orchestrator.create_agent_loop(
            role=role,
            tools=tools,
            tool_dispatcher=dispatch_tool,
            callbacks=callbacks,
            session_key=sk,
        )

    def _get_or_create_loop():
        sk = _cli_session_key()
        loop = loops_by_session.get(sk)
        if loop is None:
            loop = _create_loop()
            loops_by_session[sk] = loop
        return loop

    def _rebuild_loop():
        nonlocal agent_loop
        sk = _cli_session_key()
        old = loops_by_session.pop(sk, None)
        if old is not None:
            _trigger_session_end(orchestrator, old)
        agent_loop = _create_loop()
        loops_by_session[sk] = agent_loop
        return agent_loop

    agent_loop = _get_or_create_loop()

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
            handled = _handle_slash_command(
                user_input, orchestrator, console, agent_loop=agent_loop
            )
            if handled == "quit":
                _trigger_session_end(orchestrator, agent_loop)
                return 0
            if handled == "rebuild":
                # _rebuild_loop() already runs post_session on the old loop once.
                agent_loop = _rebuild_loop()
            elif handled == "switch_project":
                agent_loop = _get_or_create_loop()
            if handled:
                continue
            console.print(
                f"[yellow]未知命令: {user_input.split(maxsplit=1)[0]}[/yellow]"
            )
            console.print("[dim]输入 /help 查看可用命令[/dim]")
            continue

        from butler.gateway.hooks import apply_pre_llm_context

        augmented = apply_pre_llm_context(
            orchestrator.inject_skill_context(user_input),
            orchestrator=orchestrator,
        )
        ui.print_user_message(user_input)
        ui.begin_turn()
        stream = None

        try:
            from butler.cli.stream import StreamRenderer
            from butler.execution_context import use_execution_context
            from butler.session_lifecycle import attach_turn_memory_prefetch

            stream = StreamRenderer(console, title=settings.butler_name or "Butler")
            agent_loop.callbacks = ui.build_callbacks(stream)

            agent_loop = _get_or_create_loop()
            attach_turn_memory_prefetch(agent_loop, orchestrator, user_input, role="butler")
            cli_sk = _cli_session_key()
            with use_execution_context(orchestrator, session_key=cli_sk):
                result = agent_loop.run(augmented)

            ui.finish_turn(result, stream)

            with use_execution_context(orchestrator, session_key=cli_sk):
                _sync_memory(
                    orchestrator,
                    user_input,
                    result.final_response or "",
                    interrupted=result.status == LoopStatus.INTERRUPTED,
                    status=result.status,
                )
                from butler.session_lifecycle import queue_prefetch_after_turn

                queue_prefetch_after_turn(
                    orchestrator,
                    user_input,
                    role="butler",
                    session_id=cli_sk,
                )

        except KeyboardInterrupt:
            console.print("\n[dim]已中断[/dim]")
            agent_loop.interrupt()
            from butler.core.agent_loop import LoopResult
            if stream is not None:
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
    *,
    agent_loop: Any | None = None,
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
            "  /health         — 运行时诊断（压缩、工具审计等）\n"
            "  /detail         — 上一次委派的详细报告\n"
            "  /workflow       — 列出或运行项目工作流 (DAG)\n"
            "  /steer <文本>   — 向运行中的 Agent 插入指引（不打断工具）\n"
            "  /记忆待审       — 列出项目 MEMORY Pending 队列\n"
            "  /批准记忆 <序号|全部> — 批准待审记忆\n"
            "  /拒绝记忆 <序号|全部> — 拒绝待审记忆（清理 Pending 向量）\n"
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
            console.print(
                f"[green]已切换到项目: {new}[/green] "
                "[dim]（该项目有独立对话历史）[/dim]"
            )
            return "switch_project"
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
            from butler.session_keys import build_session_key
            from butler.session_lifecycle import clear_session_boundary_memory

            cli_sk = build_session_key(
                platform="cli",
                chat_id=orchestrator.user_id,
                project=orchestrator.project_manager.current_project or "",
            )
            clear_session_boundary_memory(orchestrator, cli_sk)
            console.print("[dim]已清空对话历史[/dim]")
            return "rebuild"

        if command in ("/switch", "/切换") and arg:
            from butler.project_lead import lead_mode_switch_suffix

            note = lead_mode_switch_suffix(orchestrator.project_manager.current_project or "")
            if note:
                console.print(f"[dim]{note.strip()}[/dim]")

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

    from butler.gateway.memory_commands import handle_memory_pending_command

    mem_resp = handle_memory_pending_command(orchestrator, command, arg)
    if mem_resp is not None:
        console.print(mem_resp)
        return "handled"

    if command in ("/health", "/诊断"):
        from butler.gateway.message_handler import ButlerMessageHandler

        handler = ButlerMessageHandler(channel="cli")
        handler._orchestrator = orchestrator
        if agent_loop is not None:
            loop_diag = dict(getattr(agent_loop, "diagnostics", {}) or {})
            handler._health_by_session["cli"] = {
                "session_key": "cli",
                "platform": "cli",
                "hygiene_compressed": loop_diag.get("hygiene_compressed"),
                "schema_recovered": loop_diag.get("schema_recovered"),
                "schema_keywords_stripped": loop_diag.get("schema_keywords_stripped"),
                "skill_context_injected": loop_diag.get("skill_context_injected"),
                "skill_matches": loop_diag.get("skill_matches"),
                "memory_context_injected": loop_diag.get("memory_context_injected"),
                "memory_prefetch_chars": loop_diag.get("memory_prefetch_chars"),
                "memory_context_chars": loop_diag.get("memory_context_chars"),
                "loop": loop_diag,
            }
        console.print(handler._format_health_summary("cli"))
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
        from butler.report_format import parse_detail_section
        try:
            report = get_last_report()
            if report:
                from butler.report import format_detail
                console.print(format_detail(report, section=parse_detail_section(arg)))
            else:
                console.print("[dim]暂无可展示的详细报告[/dim]")
        except Exception:
            console.print("[dim]报告系统不可用[/dim]")
        return "handled"

    if command in ("/workflow", "/工作流"):
        from butler.session_keys import build_session_key
        from butler.workflows.commands import handle_workflow_command

        cli_sk = build_session_key(
            platform="cli",
            chat_id=orchestrator.user_id,
            project=orchestrator.project_manager.current_project or "",
        )
        out = handle_workflow_command(orchestrator, arg, session_key=cli_sk)
        console.print(out)
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
    from butler.tools.registry import dispatch_tool
    from butler.tools.project_tools import get_current_project_tools
    from rich.console import Console

    console = Console(stderr=True)
    orch = ButlerOrchestrator(user_id="owner", channel="cli")
    augmented = orch.inject_skill_context(ns.message)
    ui = ChatSessionUI(console, stream_title="exec")
    ui.print_user_message(ns.message)
    stream = ui.begin_turn()

    agent_loop = orch.create_agent_loop(
        role="butler",
        tools=get_current_project_tools(role="butler"),
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


def _print_wechat_setup_success(creds: dict[str, str]) -> None:
    """Human-readable next steps after QR login."""
    account_id = creds["account_id"]
    token = creds["token"]
    base_url = creds.get("base_url") or "https://ilinkai.weixin.qq.com"
    print("\n微信 iLink 绑定成功。")
    print(f"  Account ID: {account_id}")
    print(f"  Base URL:   {base_url}")
    print(f"\n凭证已写入 ~/.butler/wechat/accounts/{account_id}.json")
    print("\n启动网关:")
    print("  butler gateway")
    print("  # 生产推荐: bash scripts/install-butler-gateway-service.sh")
    print("  # 日常: bash scripts/butler-gateway-ops.sh restart")
    print("\n可将以下内容加入项目 .env（也可只设 WECHAT_ACCOUNT_ID，token 会从 accounts 目录读取）:")
    print(f"WECHAT_ACCOUNT_ID={account_id}")
    print(f"WECHAT_TOKEN={token}")
    if base_url != "https://ilinkai.weixin.qq.com":
        print(f"WECHAT_BASE_URL={base_url}")
    print("\n勿与 Hermes 共用同一 Bot；Hermes 凭证在 ~/.hermes/，Butler 在 ~/.butler/。")


def _merge_wechat_env_file(env_path: Path, creds: dict[str, str]) -> None:
    """Upsert WECHAT_* lines in a dotenv file."""
    base_url = creds.get("base_url") or "https://ilinkai.weixin.qq.com"
    updates = {
        "WECHAT_ACCOUNT_ID": creds["account_id"],
        "WECHAT_TOKEN": creds["token"],
        "WEIXIN_ACCOUNT_ID": creds["account_id"],
        "WEIXIN_TOKEN": creds["token"],
    }
    if base_url != "https://ilinkai.weixin.qq.com":
        updates["WECHAT_BASE_URL"] = base_url
        updates["WEIXIN_BASE_URL"] = base_url

    lines: list[str] = []
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").splitlines()

    seen: set[str] = set()
    out: list[str] = []
    for line in lines:
        key = line.split("=", 1)[0].strip() if "=" in line and not line.lstrip().startswith("#") else ""
        if key in updates:
            if key not in seen:
                out.append(f"{key}={updates[key]}")
                seen.add(key)
            continue
        out.append(line)

    for key, value in updates.items():
        if key not in seen:
            out.append(f"{key}={value}")

    env_path.parent.mkdir(parents=True, exist_ok=True)
    env_path.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")
    print(f"\n已更新 {env_path}")


def _cmd_memory_reindex(ns: argparse.Namespace) -> int:
    from rich.console import Console

    from butler.config import get_butler_home
    from butler.memory.reindex import ensure_semantic_enabled_msg, reindex_semantic_memory

    hint = ensure_semantic_enabled_msg()
    if hint:
        console = Console()
        console.print(f"[yellow]{hint}[/yellow]")
        return 2

    result = reindex_semantic_memory(
        get_butler_home(),
        tenant_id=str(ns.tenant or "default"),
        project_name=(ns.project or "").strip() or None,
        index_experience=True,
        index_project_memory=not ns.experience_only,
        clear_vectors=not ns.no_clear,
    )
    console = Console()
    if not result.get("ok"):
        console.print(f"[red]{result.get('error', 'reindex failed')}[/red]")
        return 1
    console.print(
        "[bold]语义向量索引已重建[/bold]\n"
        f"  租户: {result.get('tenant_id')}\n"
        f"  模型: {result.get('model_id')}\n"
        f"  清空旧条: {result.get('cleared', 0)}\n"
        f"  experience: {result.get('indexed_experience', 0)} "
        f"(跳过 conversation {result.get('skipped_conversation', 0)})\n"
        f"  项目 MEMORY 条目: {result.get('indexed_project_bullets', 0)} "
        f"(扫描项目 {result.get('projects_scanned', 0)})\n"
        f"  向量表合计: {result.get('vector_rows', 0)}"
    )
    return 0


def _cmd_wechat_setup(ns: argparse.Namespace) -> int:
    """Interactive WeChat iLink QR login (Hermes-style setup wizard)."""
    import asyncio

    from butler.config import get_butler_home
    from butler.gateway.platforms.wechat import check_wechat_requirements, qr_login

    if not check_wechat_requirements():
        print(
            "微信扫码需要可选依赖: pip install -e \".[wechat]\"",
            file=sys.stderr,
        )
        return 1

    async def _run() -> dict[str, str] | None:
        return await qr_login(
            str(get_butler_home()),
            bot_type=str(getattr(ns, "bot_type", "3") or "3"),
            timeout_seconds=int(getattr(ns, "timeout", 480) or 480),
        )

    try:
        creds = asyncio.run(_run())
    except KeyboardInterrupt:
        print("\n已取消。", file=sys.stderr)
        return 130

    if not creds:
        print("登录失败或超时。", file=sys.stderr)
        return 1

    _print_wechat_setup_success(creds)

    write_env = getattr(ns, "write_env", None)
    if write_env is not None:
        env_path = Path(write_env) if str(write_env).strip() else _REPO_ROOT / ".env"
        if not env_path.is_absolute():
            env_path = (_REPO_ROOT / env_path).resolve()
        _merge_wechat_env_file(env_path, creds)

    return 0


def _cmd_runtime_list(ns: argparse.Namespace) -> int:
    from butler.runtime.service import format_jobs_list_text

    print(format_jobs_list_text(ns.project.strip()))
    return 0


def _cmd_runtime_run(ns: argparse.Namespace) -> int:
    from butler.runtime.service import run_job

    out = run_job(
        ns.project.strip(),
        ns.job_id.strip(),
        skip_notify=bool(ns.no_notify),
        force=bool(ns.force),
    )
    if out.get("error"):
        print(out["error"], file=sys.stderr)
        return 1
    status = "ok" if out.get("success") else "failed"
    print(f"[{status}] {out.get('job_id')}")
    if out.get("summary"):
        print(out["summary"])
    if out.get("record_path"):
        print(f"audit: {out['record_path']}")
    return 0 if out.get("success") else 2


def _cmd_runtime_due(ns: argparse.Namespace) -> int:
    from butler.runtime.service import run_due_jobs

    results = run_due_jobs(
        ns.project.strip(),
        skip_notify=bool(ns.no_notify),
    )
    if not results:
        print("没有到期的任务。")
        return 0
    exit_code = 0
    for out in results:
        jid = out.get("job_id") or "?"
        if out.get("error"):
            print(f"{jid}: error — {out['error']}", file=sys.stderr)
            exit_code = 1
            continue
        if out.get("pending_approval"):
            note = "notified" if out.get("notified") else "skipped-notify-cooldown"
            print(f"{jid}: [pending-approval] ({note})")
            continue
        status = "ok" if out.get("success") else "failed"
        print(f"{jid}: [{status}]")
        if not out.get("success"):
            exit_code = 2
    return exit_code


def _cmd_runtime_approve(ns: argparse.Namespace) -> int:
    from butler.runtime.service import approve_and_run

    out = approve_and_run(
        ns.project.strip(),
        ns.job_id.strip(),
        run_now=not bool(ns.approve_only),
        skip_notify=bool(ns.no_notify),
    )
    if out.get("error"):
        print(out["error"], file=sys.stderr)
        return 1
    if out.get("message"):
        print(out["message"])
        return 0
    status = "ok" if out.get("success") else "failed"
    print(f"[{status}] {out.get('job_id')}")
    if out.get("summary"):
        print(out["summary"])
    return 0 if out.get("success") else 2


def _cmd_gateway(ns: argparse.Namespace) -> int:
    """Start WeChat-only Butler gateway (iLink)."""
    os.environ["BUTLER_GATEWAY_ACTIVE"] = "1"
    remainder = list(getattr(ns, "gateway_remainder", None) or [])
    legacy = [x for x in remainder if x in ("--hermes-fallback", "--native-only")]
    if legacy:
        print(
            "Butler 网关仅支持微信，已移除 --hermes-fallback / --native-only。"
            "请使用: butler gateway",
            file=sys.stderr,
        )
        return 2

    from butler.gateway.platform_policy import format_unsupported_error, normalize_platforms, unsupported_platforms
    from butler.gateway.runner import run_gateway_blocking

    platforms = normalize_platforms(ns.platforms or "")
    bad = unsupported_platforms(platforms)
    if bad:
        print(format_unsupported_error(bad), file=sys.stderr)
        return 2
    return run_gateway_blocking(["wechat"])


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

    gw = sub.add_parser("gateway", help="启动微信消息网关（iLink，仅此平台）")
    gw.add_argument(
        "--platforms",
        default="",
        help="仅支持 wechat（默认）；其他平台名将被拒绝",
    )
    gw.add_argument(
        "gateway_remainder",
        nargs=argparse.REMAINDER,
        help=argparse.SUPPRESS,
    )
    gw.set_defaults(func=_cmd_gateway)

    wx = sub.add_parser(
        "wechat-setup",
        help="微信 iLink 扫码绑定 Bot（保存到 ~/.butler/wechat/accounts/）",
    )
    wx.add_argument(
        "--timeout",
        type=int,
        default=480,
        help="扫码等待秒数（默认 480）",
    )
    wx.add_argument(
        "--bot-type",
        default="3",
        help="iLink bot_type 参数（默认 3）",
    )
    wx.add_argument(
        "--write-env",
        nargs="?",
        const=".env",
        default=None,
        metavar="PATH",
        help="将 WECHAT_ACCOUNT_ID/WECHAT_TOKEN 写入 .env（默认项目根 .env）",
    )
    wx.set_defaults(func=_cmd_wechat_setup)

    ri = sub.add_parser(
        "memory-reindex",
        help="重建本地语义向量索引（需 BUTLER_SEMANTIC_MEMORY=1，无云存储）",
    )
    ri.add_argument(
        "--tenant",
        default="default",
        help="租户 id（默认 default）",
    )
    ri.add_argument(
        "--project",
        default="",
        help="仅重建指定项目名的 MEMORY.md 条目（空=扫描 BUTLER_PROJECTS_DIR 下全部）",
    )
    ri.add_argument(
        "--experience-only",
        action="store_true",
        help="只索引 experience.db，跳过项目 MEMORY",
    )
    ri.add_argument(
        "--no-clear",
        action="store_true",
        help="不清空现有向量表（增量 upsert，可能残留已删条目）",
    )
    ri.set_defaults(func=_cmd_memory_reindex)

    rt = sub.add_parser("runtime", help="项目定时任务（cron/批准/微信推送）")
    rt_sub = rt.add_subparsers(dest="runtime_cmd", required=True)

    rt_list = rt_sub.add_parser("list", help="列出项目 runtime/jobs.yaml 任务")
    rt_list.add_argument("--project", required=True, help="项目名称，如 灵文1号")
    rt_list.set_defaults(func=_cmd_runtime_list)

    rt_run = rt_sub.add_parser("run", help="执行单个任务（改盘须已批准）")
    rt_run.add_argument("job_id", help="jobs.yaml 中的 id")
    rt_run.add_argument("--project", required=True)
    rt_run.add_argument(
        "--no-notify",
        action="store_true",
        help="不推送微信摘要",
    )
    rt_run.add_argument(
        "--force",
        action="store_true",
        help="允许运行 enabled:false 的任务（改盘仍须批准）",
    )
    rt_run.set_defaults(func=_cmd_runtime_run)

    rt_due = rt_sub.add_parser("due", help="执行当前到期的任务（改盘仅推送待批准）")
    rt_due.add_argument("--project", required=True)
    rt_due.add_argument(
        "--no-notify",
        action="store_true",
        help="不推送微信摘要",
    )
    rt_due.set_defaults(func=_cmd_runtime_due)

    rt_ap = rt_sub.add_parser("approve", help="批准改盘任务并可立即执行")
    rt_ap.add_argument("job_id")
    rt_ap.add_argument("--project", required=True)
    rt_ap.add_argument(
        "--approve-only",
        action="store_true",
        help="仅写入批准，不立即执行",
    )
    rt_ap.add_argument("--no-notify", action="store_true")
    rt_ap.set_defaults(func=_cmd_runtime_approve)

    return p


def main(argv: Sequence[str] | None = None) -> None:
    args = _build_parser().parse_args(argv)
    code = args.func(args)
    raise SystemExit(code)


if __name__ == "__main__":
    main()

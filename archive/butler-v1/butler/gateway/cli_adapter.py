"""CLI/TUI adapter - interactive terminal interface with enhanced visual experience.

v4: Hermes/Claude Code-inspired UX — streaming with box chrome, live spinner
    during tool calls, Markdown rendering, status bar, and color-coded output.
"""

from __future__ import annotations

import asyncio
import itertools
import time
from typing import Any

from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import ANSI
from prompt_toolkit.history import FileHistory
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.patch_stdout import patch_stdout
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box

from butler.config.settings import ModelConfig, settings
from butler.core.butler import Butler
from butler.gateway.base import BaseAdapter

console = Console()

_ACCENT = "cyan"
_DIM = "dim"
_BORDER_TOP    = "╭─ {title} ─"
_BORDER_BOTTOM = "╰─"
_TOOL_PREFIX   = "  ┊"

_SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
_TOOL_EMOJI = {
    "read_file": "📄", "write_file": "✏️", "edit_file": "✏️",
    "list_directory": "📁", "search_code": "🔍", "run_shell": "⚡",
    "git_status": "📊", "git_diff": "📊", "git_commit": "💾",
    "remember": "🧠", "recall": "🧠",
    "delegate_to_dev_agent": "🤖", "delegate_to_content_agent": "🤖",
    "delegate_to_review_agent": "🤖",
    "list_projects": "📋", "switch_project": "🔄", "get_project_status": "📋",
    "skill_list": "📚", "skill_create": "📚", "skill_view": "📚",
}


class _StreamBox:
    """Manages the visual chrome around a streaming assistant response."""

    def __init__(self, title: str = ""):
        self._title = title
        self._started = False
        self._line_buf = ""

    def open(self) -> None:
        if self._started:
            return
        self._started = True
        label = self._title or "回复"
        console.print(f"[{_ACCENT}]╭─ {label} ─{'─' * max(0, 50 - len(label))}[/{_ACCENT}]")

    def write(self, text: str) -> None:
        self.open()
        self._line_buf += text
        while "\n" in self._line_buf:
            line, self._line_buf = self._line_buf.split("\n", 1)
            console.print(f"[{_ACCENT}]│[/{_ACCENT}] {line}")

    def close(self) -> None:
        if not self._started:
            return
        if self._line_buf:
            console.print(f"[{_ACCENT}]│[/{_ACCENT}] {self._line_buf}")
            self._line_buf = ""
        console.print(f"[{_ACCENT}]╰{'─' * 55}[/{_ACCENT}]")


class _ToolSpinner:
    """Threaded spinner that shows tool execution progress."""

    def __init__(self):
        self._task: asyncio.Task | None = None
        self._tool_name = ""
        self._tool_brief = ""
        self._start_time = 0.0
        self._step = 0
        self._active = False
        self._frames = itertools.cycle(_SPINNER_FRAMES)

    def start(self, tool_name: str, brief: str, step: int) -> None:
        self._tool_name = tool_name
        self._tool_brief = brief[:50]
        self._start_time = time.monotonic()
        self._step = step
        self._active = True

    def stop(self) -> None:
        if self._active:
            elapsed = time.monotonic() - self._start_time
            emoji = _TOOL_EMOJI.get(self._tool_name, "🔧")
            console.print(
                f"  [dim]┊[/dim] {emoji} [bold]{self._tool_name}[/bold]"
                f"  [dim]{self._tool_brief}[/dim]"
                f"  [{_ACCENT}]{elapsed:.1f}s[/{_ACCENT}]"
            )
            self._active = False

    def get_line(self) -> str:
        if not self._active:
            return ""
        frame = next(self._frames)
        elapsed = time.monotonic() - self._start_time
        emoji = _TOOL_EMOJI.get(self._tool_name, "🔧")
        return (
            f"\r  ┊ {frame} {emoji} {self._tool_name}"
            f"  {self._tool_brief}  {elapsed:.1f}s"
        )


class CLIAdapter(BaseAdapter):
    """Interactive CLI adapter with enhanced visual experience."""

    name = "cli"

    def __init__(self, butler: Butler | None = None):
        self.butler = butler
        history_path = settings.butler_home / "cli_history"
        self.prompt_session: PromptSession = PromptSession(
            history=FileHistory(str(history_path)),
            auto_suggest=AutoSuggestFromHistory(),
        )
        self._running = False
        self._spinner = _ToolSpinner()
        self._current_stream_box: _StreamBox | None = None
        self._tool_step = 0

    async def start(self) -> None:
        if self.butler is None:
            self.butler = Butler(channel="cli")

        self._running = True
        self._print_welcome()

        while self._running:
            try:
                user_input = await self._get_input()
                if user_input is None:
                    break
                user_input = user_input.strip()
                if not user_input:
                    continue
                if self._handle_command(user_input):
                    continue
                await self._process_message(user_input)
            except KeyboardInterrupt:
                console.print(f"\n[{_DIM}]Ctrl+C 退出[/{_DIM}]")
                break
            except EOFError:
                break

        await self.stop()

    async def stop(self) -> None:
        self._running = False
        if self.butler:
            await self.butler.close()
        console.print(f"\n[{_DIM}]👋 {settings.butler_name}> 再见，{settings.owner_name}。[/{_DIM}]")

    async def send(self, user_id: str, content: str, **kwargs: Any) -> None:
        console.print()
        console.print(Markdown(content))

    async def _get_input(self) -> str | None:
        try:
            loop = asyncio.get_running_loop()
            prompt_text = f"\n\033[1;32m{settings.owner_name}\033[0m\033[2m ❯\033[0m "
            return await loop.run_in_executor(
                None, lambda: self.prompt_session.prompt(ANSI(prompt_text)),
            )
        except (KeyboardInterrupt, EOFError):
            return None

    async def _process_message(self, user_input: str) -> None:
        self._tool_step = 0
        stream_box = _StreamBox(settings.butler_name)
        self._current_stream_box = stream_box
        has_streamed = False

        def on_agent_progress(turn: int, tool_name: str, brief: str):
            self._tool_step += 1
            if stream_box._started:
                stream_box.close()
            self._spinner.stop()
            self._spinner.start(tool_name, brief, self._tool_step)

        self.butler.set_progress_handler(on_agent_progress)

        def on_stream(text: str):
            nonlocal has_streamed
            self._spinner.stop()
            has_streamed = True
            stream_box.write(text)

        response = await self.butler.chat(user_input, stream_callback=on_stream)

        self.butler.set_progress_handler(None)
        self._spinner.stop()

        if has_streamed:
            stream_box.close()
        else:
            console.print()
            md = Markdown(response)
            console.print(
                Panel(
                    md,
                    title=f"[bold {_ACCENT}]{settings.butler_name}[/bold {_ACCENT}]",
                    border_style=_ACCENT,
                    padding=(0, 1),
                    box=box.ROUNDED,
                )
            )

        self._current_stream_box = None

    def _handle_command(self, text: str) -> bool:
        if text in ("/quit", "/exit", "/q"):
            self._running = False
            return True

        if text == "/new":
            self.butler.new_session()
            console.print(f"[{_DIM}]✨ 已开始新会话（旧会话记忆已提炼保存）[/{_DIM}]")
            return True

        if text == "/projects":
            self._show_projects()
            return True

        if text.startswith("/switch "):
            name = text[8:].strip()
            from butler.core.project_manager import project_manager
            if project_manager.switch_project(name):
                console.print(f"[{_DIM}]🔄 已切换到项目: [bold]{project_manager.current_project}[/bold] (会话已隔离)[/{_DIM}]")
            else:
                console.print(f"[bold red]未找到项目: {name}[/bold red]")
            return True

        if text.startswith("/model"):
            self._handle_model_command(text)
            return True

        if text.startswith("/detail"):
            self._handle_detail_command(text)
            return True

        if text == "/help":
            self._print_help()
            return True

        if text == "/status":
            self._print_status()
            return True

        return False

    def _show_projects(self) -> None:
        from butler.core.project_manager import project_manager
        projects = project_manager.list_projects()
        if not projects:
            console.print(f"[{_DIM}]暂无项目[/{_DIM}]")
            return

        table = Table(
            box=box.SIMPLE_HEAVY, border_style="dim",
            show_header=True, header_style="bold",
        )
        table.add_column("状态", width=8)
        table.add_column("项目", style="bold")
        table.add_column("类型", style="dim")
        table.add_column("描述")

        for p in projects:
            is_current = p.name == project_manager.current_project
            name = f"[bold green]{p.name} ★[/bold green]" if is_current else p.name
            status = f"[green]{p.status}[/green]" if p.status == "active" else p.status
            table.add_row(status, name, p.type, p.description)

        console.print(table)

    def _handle_detail_command(self, text: str) -> None:
        from butler.core.report_formatter import format_detail

        result = self.butler.get_last_report()
        if result is None:
            console.print(f"[{_DIM}]没有最近的 Agent 执行记录。[/{_DIM}]")
            return

        parts = text.split(maxsplit=1)
        section = parts[1].strip() if len(parts) > 1 else ""

        if section == "log":
            if result.milestones:
                content = "\n".join(
                    f"  [dim]{i+1}.[/dim] {m}" for i, m in enumerate(result.milestones)
                )
                console.print(Panel(content, title="📋 执行步骤", border_style="dim", box=box.ROUNDED))
            else:
                console.print(f"[{_DIM}]没有执行步骤记录。[/{_DIM}]")
            return

        report = result.report
        detail_text = format_detail(report, section)
        console.print(Panel(detail_text, title="📋 详细报告", border_style=_ACCENT, box=box.ROUNDED))

    def _handle_model_command(self, text: str) -> None:
        parts = text.split()

        if len(parts) == 1:
            self._show_model_config()
            return

        if len(parts) < 3:
            console.print(f"[{_DIM}]用法: /model <层> <provider:model> 或 /model <层> <model>[/{_DIM}]")
            console.print(f"[{_DIM}]层: butler, project, dev, content, review[/{_DIM}]")
            return

        layer = parts[1]
        model_spec = parts[2]

        if ":" in model_spec:
            provider, model = model_spec.split(":", 1)
        else:
            provider = ""
            model = model_spec

        config = ModelConfig(provider=provider, model=model)

        if layer == "butler":
            settings.models.butler = config
            settings.save_butler_config()
            console.print(f"[green]✓[/green] 管家层模型已设为: [{_ACCENT}]{model_spec}[/{_ACCENT}] (已持久化)")

        elif layer in ("project", "dev", "content", "review"):
            from butler.core.project_manager import project_manager
            proj = project_manager.get_current()
            if not proj:
                console.print("[bold red]请先切换到一个项目[/bold red]")
                return
            role = layer if layer != "project" else "dev_agent"
            if layer == "content":
                role = "content_agent"
            elif layer == "review":
                role = "review_agent"
            elif layer == "dev":
                role = "dev_agent"
            proj.set_model(role, config)
            console.print(f"[green]✓[/green] 项目【{proj.name}】{role} 模型已设为: [{_ACCENT}]{model_spec}[/{_ACCENT}] (已持久化)")
        else:
            console.print(f"[bold red]未知层: {layer}。可选: butler, project, dev, content, review[/bold red]")

    def _show_model_config(self) -> None:
        from butler.core.project_manager import project_manager

        butler_mc = settings.get_model_config("butler")

        table = Table(
            title="模型配置",
            box=box.ROUNDED, border_style=_ACCENT,
            show_header=True, header_style="bold",
        )
        table.add_column("层级", style="bold")
        table.add_column("Provider")
        table.add_column("模型", style=_ACCENT)
        table.add_column("来源", style="dim")

        table.add_row("管家", butler_mc.provider, butler_mc.model, "全局配置")

        proj = project_manager.get_current()
        if proj:
            for role in ("dev_agent", "content_agent", "review_agent"):
                mc = proj.resolve_model(role)
                proj_override = proj.models.get(role)
                source = "项目覆盖" if proj_override and not proj_override.is_empty() else "继承全局"
                table.add_row(f"  {role}", mc.provider, mc.model, source)
        else:
            table.add_row("[dim]项目[/dim]", "-", "-", "未选择项目")

        console.print(table)
        console.print(f"\n  [{_DIM}]可用 Provider: {', '.join(settings.providers.keys()) or '(无)'}[/{_DIM}]")
        console.print(f"  [{_DIM}]用法: /model <层> <provider:model>[/{_DIM}]")

    def _print_welcome(self) -> None:
        from butler.core.project_manager import project_manager
        projects = project_manager.list_projects()
        current = project_manager.current_project or "未选择"
        butler_mc = settings.get_model_config("butler")

        logo = Text()
        logo.append("╔══════════════════════════════════════╗\n", style=_ACCENT)
        logo.append("║", style=_ACCENT)
        logo.append(f"  {settings.butler_name} ", style=f"bold {_ACCENT}")
        logo.append("管家系统 v0.3", style="bold white")
        logo.append("              ║\n", style=_ACCENT)
        logo.append("╚══════════════════════════════════════╝", style=_ACCENT)

        console.print()
        console.print(logo)
        console.print()

        info = Table(box=None, show_header=False, padding=(0, 2), expand=False)
        info.add_column(style="dim")
        info.add_column()
        info.add_row("当前项目", f"[bold]{current}[/bold]")
        info.add_row("项目总数", str(len(projects)))
        info.add_row("管家模型", f"[{_ACCENT}]{butler_mc.provider}:{butler_mc.model}[/{_ACCENT}]")
        info.add_row("输入", "[dim]/help 查看命令，直接输入开始对话[/dim]")
        console.print(info)
        console.print(f"\n[{_DIM}]{'─' * 55}[/{_DIM}]")

    def _print_help(self) -> None:
        table = Table(
            title="可用命令",
            box=box.ROUNDED, border_style="dim",
            show_header=True, header_style="bold",
        )
        table.add_column("命令", style="bold", width=24)
        table.add_column("说明")

        commands = [
            ("/projects", "列出所有项目"),
            ("/switch <名称>", "切换项目（会话自动隔离）"),
            ("/model", "查看各层模型配置"),
            ("/model <层> <m>", "设置指定层模型 (butler/dev/content/review)"),
            ("/detail", "查看上次 Agent 执行的完整报告"),
            ("/detail changes", "查看文件变更详情"),
            ("/detail decisions", "查看关键决策"),
            ("/detail log", "查看执行步骤日志"),
            ("/status", "查看系统状态"),
            ("/new", "新会话（自动提炼旧会话记忆）"),
            ("/help", "显示此帮助"),
            ("/quit", "退出"),
        ]
        for cmd, desc in commands:
            table.add_row(cmd, desc)

        console.print(table)
        console.print(f"\n  [{_DIM}]模型格式: provider:model (如 minimax:MiniMax-M2.7)[/{_DIM}]")
        console.print(f"  [{_DIM}]直接输入自然语言与管家对话[/{_DIM}]")

    def _print_status(self) -> None:
        from butler.core.project_manager import project_manager
        current = project_manager.current_project or "未选择"
        butler_mc = settings.get_model_config("butler")

        table = Table(
            title="系统状态",
            box=box.ROUNDED, border_style=_ACCENT,
            show_header=False, padding=(0, 2),
        )
        table.add_column(style="bold")
        table.add_column()

        table.add_row("当前项目", f"[bold]{current}[/bold]")
        table.add_row("管家模型", f"[{_ACCENT}]{butler_mc.provider}:{butler_mc.model}[/{_ACCENT}]")
        table.add_row("会话 ID", f"[dim]{self.butler.session_id[:8]}...[/dim]")
        table.add_row("可用 Provider", ", ".join(settings.providers.keys()) or "(无)")

        proj = project_manager.get_current()
        if proj:
            dev_mc = proj.resolve_model("dev_agent")
            table.add_row("DevAgent 模型", f"[{_ACCENT}]{dev_mc.provider}:{dev_mc.model}[/{_ACCENT}]")

        console.print(table)

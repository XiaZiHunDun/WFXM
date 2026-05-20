"""Wires AgentLoop callbacks to Rich CLI presentation."""

from __future__ import annotations

import json
import os
import time
from typing import TYPE_CHECKING

from butler.cli.display import (
    capture_edit_snapshot,
    format_tool_complete,
    format_tool_start,
    render_inline_diff,
)
from butler.cli.spinner import WaitSpinner
from butler.cli.stream import StreamRenderer
from butler.core.agent_loop import LoopCallbacks, LoopResult, LoopStatus
from butler.transport.error_classifier import classify_api_error

if TYPE_CHECKING:
    from rich.console import Console


class ChatSessionUI:
    """Per-chat-session UI state and LoopCallbacks factory."""

    def __init__(self, console: "Console", *, stream_title: str = "Butler") -> None:
        self.console = console
        self._stream_title = stream_title
        self._spinner = WaitSpinner()
        self._tool_times: list[tuple[float, str, dict]] = []
        self._pending_edit: tuple[str, str] | None = None

    def begin_turn(self) -> StreamRenderer:
        self._spinner.stop()
        self._tool_times.clear()
        self._pending_edit = None
        return StreamRenderer(self.console, title=self._stream_title)

    def build_callbacks(self, stream: StreamRenderer) -> LoopCallbacks:
        return LoopCallbacks(
            on_llm_start=lambda _msgs: self._spinner.start("思考中"),
            on_llm_complete=lambda _resp: self._spinner.stop(),
            on_stream_delta=stream.on_delta,
            on_tool_start=self._on_tool_start,
            on_tool_complete=self._on_tool_complete,
            on_error=self._on_error,
            on_iteration=self._on_iteration,
            on_fallback=self.notify_fallback,
        )

    def notify_fallback(self, provider: str, model: str) -> None:
        self.notify_fallback_once(provider, model)

    def notify_fallback_once(self, provider: str, model: str) -> None:
        self.console.print(
            f"  [yellow]↻ 已切换备用模型: {provider}/{model}[/yellow]",
            highlight=False,
        )

    def finish_turn(self, result: LoopResult, stream: StreamRenderer) -> None:
        self._spinner.stop()
        stream.display()
        out = getattr(stream, "_console", None) or self.console

        final = (result.final_response or "").strip()
        if final and not stream.had_body():
            stream.emit_body(final)

        streamed = stream.had_body()
        if result.final_response and not streamed:
            out.print()
            from rich.markdown import Markdown

            out.print(Markdown(result.final_response))

        show_reasoning = os.getenv("BUTLER_CLI_SHOW_REASONING", "").strip() in (
            "1",
            "true",
            "yes",
        )
        if show_reasoning and result.reasoning and result.reasoning.strip():
            out.print()
            out.print(
                f"  [dim italic]推理: {result.reasoning.strip()[:500]}[/dim italic]",
                highlight=False,
            )

        if result.tool_calls_made > 0 or result.iterations > 1:
            parts = []
            if result.iterations > 1:
                parts.append(f"{result.iterations} 轮")
            if result.tool_calls_made > 0:
                parts.append(f"{result.tool_calls_made} 工具调用")
            if result.total_tokens > 0:
                parts.append(f"{result.total_tokens:,} tokens")
            parts.append(f"{result.elapsed_seconds:.1f}s")
            out.print(f"  [dim]{'  |  '.join(parts)}[/dim]", highlight=False)

        if result.status == LoopStatus.ERROR:
            msg = result.error or "LLM 调用失败，请检查网络或 API 密钥"
            out.print(f"[bold red]错误:[/bold red] {msg}")
        elif result.status == LoopStatus.TOOL_LIMIT:
            out.print(
                f"[yellow]提示:[/yellow] 已达最大迭代次数 ({result.iterations})，任务可能未完成"
            )
        elif result.status == LoopStatus.INTERRUPTED:
            out.print("[dim]本轮已中断[/dim]")

        if result.tool_calls_made > 0 or result.final_response or streamed:
            out.print()

    def _on_tool_start(self, name: str, args: dict) -> None:
        self._spinner.stop()
        self._tool_times.append((time.monotonic(), name, dict(args)))
        snap = capture_edit_snapshot(name, args)
        if snap:
            path, before = next(iter(snap.items()))
            self._pending_edit = (path, before if before is not None else "")
        else:
            self._pending_edit = None
        self.console.print(format_tool_start(name, args), highlight=False)

    def _on_tool_complete(self, name: str, result: str) -> None:
        duration = 0.0
        args: dict = {}
        if self._tool_times:
            started, n, a = self._tool_times.pop(0)
            duration = max(time.monotonic() - started, 0.0)
            if n == name:
                args = a
        self.console.print(
            format_tool_complete(name, args, duration, result),
            highlight=False,
        )

        if name in ("write_file", "patch") and self._pending_edit:
            path, before = self._pending_edit
            self._pending_edit = None
            diff = render_inline_diff(path, before)
            if diff:
                self.console.print(diff, highlight=False)

        if name == "delegate_task":
            self._show_delegate_report(result)

    def _show_delegate_report(self, result: str) -> None:
        try:
            data = json.loads(result)
        except json.JSONDecodeError:
            return
        if data.get("error"):
            self.console.print("  [red]✗ 委派失败[/red]", highlight=False)
            return
        from butler.report import format_for_cli, get_last_report

        report = get_last_report()
        if report:
            self.console.print(format_for_cli(report), highlight=False)
        else:
            self.console.print(
                f"  [green]✓ 委派完成[/green] "
                f"({data.get('iterations', '?')} 轮, {data.get('tool_calls', '?')} 工具)",
                highlight=False,
            )

    def _on_error(self, exc: Exception, attempt: int) -> None:
        self._spinner.stop()
        classified = classify_api_error(exc)
        self.console.print(
            f"  [yellow]⚠ API 重试 {attempt} ({classified.reason.value})[/yellow]",
            highlight=False,
        )

    def _on_iteration(self, iteration: int, status: LoopStatus) -> None:
        if iteration > 1 and status == LoopStatus.RUNNING:
            self._spinner.start(f"第 {iteration} 轮")

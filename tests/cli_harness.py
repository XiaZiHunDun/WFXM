"""Harness utilities for Butler CLI scenario tests (Rich output + scripted chat)."""

from __future__ import annotations

import re
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from io import StringIO
from typing import Any
from unittest.mock import MagicMock

from rich.console import Console
from rich.panel import Panel

from butler.core.agent_loop import LoopResult, LoopStatus


def capture_console(*, width: int = 120) -> tuple[Console, StringIO]:
    """Rich Console that records rendered output (terminal-like)."""
    buf = StringIO()
    console = Console(
        file=buf,
        width=width,
        force_terminal=True,
        color_system="truecolor",
        legacy_windows=False,
    )
    return console, buf


def rendered_text(buf: StringIO) -> str:
    return buf.getvalue()


_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*m")


def plain_rendered_text(buf: StringIO) -> str:
    """Strip Rich ANSI codes so assertions can match command tokens like /projects."""
    return _ANSI_ESCAPE_RE.sub("", rendered_text(buf))


def panel_bodies(buf: StringIO) -> list[str]:
    """Extract visible panel body text from captured Rich output."""
    text = rendered_text(buf)
    bodies: list[str] = []
    for block in re.split(r"╭─+ .*? ─+╮", text):
        if "╰" not in block:
            continue
        body, _, _ = block.partition("╰")
        cleaned = "\n".join(
            line for line in body.splitlines() if not line.strip().startswith("│")
        )
        cleaned = cleaned.replace("│", "").strip()
        if cleaned:
            bodies.append(cleaned)
    return bodies


def count_substring(text: str, needle: str) -> int:
    return text.count(needle)


def assert_no_ansi_artifacts(text: str) -> None:
    """Regression: leaked CSI sequences like ?[36m from broken Rich markup."""
    assert "?[3" not in text, f"leaked partial ANSI in output: {text[:500]!r}"
    assert "\x1b[?" not in text or "[0m" in text, (
        "unexpected raw escape sequence in output"
    )


def make_loop_result(
    content: str,
    *,
    status: LoopStatus = LoopStatus.COMPLETED,
    reasoning: str = "",
    tool_calls: int = 0,
    iterations: int = 1,
) -> LoopResult:
    return LoopResult(
        status=status,
        final_response=content,
        reasoning=reasoning,
        tool_calls_made=tool_calls,
        iterations=iterations,
        total_tokens=42,
        elapsed_seconds=0.5,
    )


class ScriptedPromptSession:
    """prompt_toolkit.PromptSession stand-in with a fixed input queue."""

    def __init__(self, inputs: Sequence[str]) -> None:
        self._inputs: Iterator[str] = iter(inputs)

    def prompt(self, _prefix: str = "") -> str:
        try:
            return next(self._inputs)
        except StopIteration:
            raise EOFError from None


@dataclass
class ScriptedChatRun:
    """Artifacts from a scripted interactive chat session."""

    output: str
    orchestrator: MagicMock
    user_messages: list[str] = field(default_factory=list)
    exit_code: int = 0


def mock_orchestrator_for_chat(
    tmp_path,
    *,
    butler_name: str = "莎丽",
    project_name: str = "",
    responses: dict[str, LoopResult] | None = None,
    default_response: str = "好的。",
    on_run: Any | None = None,
) -> MagicMock:
    """Minimal orchestrator for _run_interactive_chat harness tests."""
    orch = MagicMock()  # noqa: magicmock-no-spec — CLI harness facade (orchestrator / loop)
    orch._settings.butler_home = tmp_path
    orch._settings.butler_name = butler_name
    orch.project_manager.current_project = project_name
    orch.project_manager.list_projects.return_value = []
    orch.project_manager.switch_project.return_value = False
    orch._run_log: list[str] = []
    orch._model_credentials.return_value = {
        "provider": "minimax",
        "model": "MiniMax-M2.7",
    }
    orch.inject_skill_context.side_effect = lambda msg: msg

    lookup: dict[str, LoopResult] = dict(responses or {})

    def _resolve(user_text: str) -> LoopResult:
        for key, result in lookup.items():
            if key in user_text:
                return result
        return make_loop_result(default_response)

    loop_holder: dict[str, Any] = {"loop": None}

    filler = "x" * 80

    def _create_loop(**_kwargs):
        loop = MagicMock()  # noqa: magicmock-no-spec — CLI harness facade (orchestrator / loop)
        loop.messages = [
            {"role": "user", "content": filler},
            {"role": "assistant", "content": filler},
            {"role": "user", "content": filler},
            {"role": "assistant", "content": filler},
            {"role": "user", "content": filler},
            {"role": "assistant", "content": filler},
        ]
        loop.diagnostics = {}
        loop.config.stream = True

        def _run(message: str) -> LoopResult:
            orch._run_log.append(message)
            if on_run is not None:
                custom = on_run(message, loop)
                if custom is not None:
                    return custom
            loop.messages.append({"role": "user", "content": message})
            result = _resolve(message)
            loop.messages.append(
                {"role": "assistant", "content": result.final_response or ""}
            )
            cb = loop.callbacks
            if cb and cb.on_stream_delta and result.final_response:
                for chunk in _chunk_text(result.final_response, size=4):
                    cb.on_stream_delta(chunk)
            return result

        loop.run.side_effect = _run
        loop_holder["loop"] = loop
        return loop

    orch.create_agent_loop.side_effect = _create_loop
    orch._loop_holder = loop_holder
    return orch


def _chunk_text(text: str, *, size: int) -> list[str]:
    return [text[i : i + size] for i in range(0, len(text), size)]


def run_scripted_interactive_chat(
    orchestrator: MagicMock,
    inputs: Sequence[str],
    *,
    patch_stdout_during_turn: bool = True,
    patch_sync_memory: bool = True,
    patch_prefetch: bool = True,
) -> ScriptedChatRun:
    """Drive _run_interactive_chat; return output and orchestrator run log."""
    from unittest.mock import patch

    import rich.console

    from butler.main import _run_interactive_chat

    console_buf = StringIO()
    _RealConsole = rich.console.Console

    def _recording_console(*args, **kwargs):
        return _RealConsole(
            file=console_buf,
            width=120,
            force_terminal=True,
            color_system="truecolor",
        )

    patches = [
        patch(
            "prompt_toolkit.PromptSession",
            lambda *a, **k: ScriptedPromptSession(inputs),
        ),
        patch.object(rich.console, "Console", _recording_console),
    ]
    if patch_sync_memory:
        patches.append(patch("butler.main._sync_memory"))
    if patch_prefetch:
        patches.append(patch("butler.session.lifecycle.attach_turn_memory_prefetch"))
    if not patch_stdout_during_turn:
        patches.append(
            patch("prompt_toolkit.patch_stdout.patch_stdout", lambda: _null_context())
        )

    for p in patches:
        p.start()
    try:
        code = _run_interactive_chat(orchestrator)
    finally:
        for p in reversed(patches):
            p.stop()

    return ScriptedChatRun(
        output=rendered_text(console_buf),
        orchestrator=orchestrator,
        user_messages=list(orchestrator._run_log),
        exit_code=code,
    )


def assert_welcome_banner(text: str, *, butler_name: str = "莎丽") -> None:
    assert "Butler v4" in text or "Butler AI" in text
    assert butler_name in text
    assert "项目:" in text or "项目" in text
    assert "模型:" in text or "模型" in text


def finish_turn_with_result(
    result: LoopResult,
    *,
    stream_chunks: Sequence[str] | None = None,
    title: str = "莎丽",
) -> str:
    console, buf = capture_console()
    from butler.cli.session_ui import ChatSessionUI
    from butler.cli.stream import StreamRenderer

    ui = ChatSessionUI(console, stream_title=title)
    stream = StreamRenderer(console, title=title, mode="buffer")
    for chunk in stream_chunks or ():
        stream.on_delta(chunk)
    ui.finish_turn(result, stream)
    return rendered_text(buf)


def invoke_ui_tool_callbacks(
    ui: Any,
    stream: Any,
    *,
    tool_name: str,
    args: dict,
    result: str = '{"success": true}',
) -> str:
    """Fire tool start/complete callbacks; return captured console text."""
    console, buf = capture_console()
    ui.console = console
    stream._console = console
    cb = ui.build_callbacks(stream)
    assert cb.on_tool_start and cb.on_tool_complete
    cb.on_tool_start(tool_name, args)
    cb.on_tool_complete(tool_name, result)
    return rendered_text(buf)


class _null_context:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def finish_turn_capture(
    *,
    stream_chunks: Sequence[str] | None = None,
    final_response: str = "",
    title: str = "莎丽",
    reasoning: str = "hidden chain",
) -> str:
    """Run ChatSessionUI.finish_turn and return rendered output."""
    from butler.cli.session_ui import ChatSessionUI
    from butler.cli.stream import StreamRenderer

    console, buf = capture_console()
    ui = ChatSessionUI(console, stream_title=title)
    stream = StreamRenderer(console, title=title, mode="buffer")
    for chunk in stream_chunks or ():
        stream.on_delta(chunk)
    ui.finish_turn(
        make_loop_result(final_response, reasoning=reasoning),
        stream,
    )
    return rendered_text(buf)


def panels_from_console(console: Console, call_args_list) -> list[Panel]:
    return [
        c.args[0]
        for c in call_args_list
        if c.args and isinstance(c.args[0], Panel)
    ]


def run_live_scripted_chat(
    inputs: Sequence[str],
    *,
    user_id: str = "owner",
    channel: str = "cli",
    patch_sync_memory: bool = False,
    patch_prefetch: bool = False,
    patch_auxiliary_post_session: bool = True,
) -> ScriptedChatRun:
    """Drive ``_run_interactive_chat`` with a real ``ButlerOrchestrator`` (live LLM)."""
    from unittest.mock import patch

    import rich.console

    from butler.config import reload_butler_settings
    from butler.main import _run_interactive_chat
    from butler.orchestrator import ButlerOrchestrator

    reload_butler_settings()
    orch = ButlerOrchestrator(user_id=user_id, channel=channel)
    user_log: list[str] = []
    _inject = orch.inject_skill_context

    def _logged_inject(message: str) -> str:
        user_log.append(message)
        return _inject(message)

    orch.inject_skill_context = _logged_inject  # type: ignore[method-assign]

    console_buf = StringIO()
    _RealConsole = rich.console.Console

    def _recording_console(*args, **kwargs):
        return _RealConsole(
            file=console_buf,
            width=120,
            force_terminal=True,
            color_system="truecolor",
        )

    patches = [
        patch(
            "prompt_toolkit.PromptSession",
            lambda *a, **k: ScriptedPromptSession(inputs),
        ),
        patch.object(rich.console, "Console", _recording_console),
    ]
    if patch_sync_memory:
        patches.append(patch("butler.main._sync_memory"))
    if patch_prefetch:
        patches.append(patch("butler.session.lifecycle.attach_turn_memory_prefetch"))
    if patch_auxiliary_post_session:
        patches.append(
            patch(
                "butler.transport.auxiliary_client.auxiliary_complete",
                return_value='{"updates": []}',
            )
        )

    for p in patches:
        p.start()
    try:
        code = _run_interactive_chat(orch)
    finally:
        for p in reversed(patches):
            p.stop()

    return ScriptedChatRun(
        output=rendered_text(console_buf),
        orchestrator=orch,
        user_messages=list(user_log),
        exit_code=code,
    )

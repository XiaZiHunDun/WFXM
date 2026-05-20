"""Line-buffered streaming output with optional box chrome."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, TextIO

from butler.transport.content_sanitize import sanitize_stream_delta

if TYPE_CHECKING:
    from rich.console import Console


class StreamRenderer:
    """Buffers assistant stream text and renders a plain box after the turn.

    Tokens are accumulated during ``patch_stdout()`` (no live stderr writes).
    ``display()`` flushes the box once, outside the patched stdout window, so
    prompt_toolkit cannot corrupt or erase streamed lines.
    """

    def __init__(
        self,
        console: "Console | None" = None,
        *,
        title: str = "Butler",
        output: TextIO | None = None,
    ) -> None:
        self._console = console
        self._out: TextIO = output or sys.stderr
        self._title = title
        self._open = False
        self._displayed = False
        self._buffer = ""

    @property
    def text(self) -> str:
        return self._buffer

    def had_body(self) -> bool:
        return bool(self._buffer.strip())

    def _writeln(self, text: str) -> None:
        self._out.write(text + "\n")
        self._out.flush()

    def _open_box(self) -> None:
        if self._open:
            return
        self._open = True
        label = self._title
        pad = max(0, 48 - len(label))
        self._writeln(f"╭─ {label} ─{'─' * pad}")

    def _close_box(self) -> None:
        if not self._open:
            return
        self._writeln(f"╰{'─' * 52}")
        self._open = False

    def display(self) -> None:
        """Render buffered text once (safe to call outside patch_stdout)."""
        if self._displayed:
            return
        self._displayed = True

        body = self._buffer.strip()
        if not body:
            self._open = False
            return

        self._open_box()
        for line in body.splitlines():
            if line.strip():
                self._writeln(f"│ {line}")
        self._close_box()

    def emit_body(self, content: str) -> None:
        """Fallback when streaming produced no visible body (e.g. thinking-only stream)."""
        text = (content or "").strip()
        if not text:
            return
        self._displayed = False
        self._open = False
        self._buffer = text
        self.display()

    def on_delta(self, delta: str | None) -> None:
        if delta is None:
            self.display()
            return
        if not delta:
            return
        cleaned = sanitize_stream_delta(delta)
        if cleaned:
            self._buffer += cleaned

    def close(self) -> None:
        self.display()

"""Line-buffered streaming output with optional box chrome."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, TextIO

from butler.transport.content_sanitize import sanitize_stream_delta

if TYPE_CHECKING:
    from rich.console import Console


class StreamRenderer:
    """Buffers stream tokens, prints line-by-line inside a light box.

    Uses plain ``stderr`` writes (no Rich ANSI) so output stays readable under
    ``prompt_toolkit.patch_stdout`` and in terminals that mishandle escape codes.
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
        self._line_buf = ""
        self._full_text: list[str] = []

    @property
    def text(self) -> str:
        return "".join(self._full_text) + self._line_buf

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

    def on_delta(self, delta: str | None) -> None:
        if delta is None:
            self.close()
            return
        if not delta:
            return
        cleaned = sanitize_stream_delta(delta)
        if not cleaned:
            return
        self._full_text.append(cleaned)
        self._open_box()
        self._line_buf += cleaned
        while "\n" in self._line_buf:
            line, self._line_buf = self._line_buf.split("\n", 1)
            if not line.strip():
                continue
            self._writeln(f"│ {line}")

    def close(self) -> None:
        if not self._open:
            if self._line_buf:
                self._full_text.append(self._line_buf)
                self._line_buf = ""
            return
        if self._line_buf.strip():
            self._writeln(f"│ {self._line_buf}")
            self._full_text.append(self._line_buf)
            self._line_buf = ""
        elif self._line_buf:
            self._full_text.append(self._line_buf)
            self._line_buf = ""
        self._writeln(f"╰{'─' * 52}")
        self._open = False

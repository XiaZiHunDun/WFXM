"""Line-buffered streaming output for Butler CLI (live + buffer modes)."""

from __future__ import annotations

import os
import shutil
from typing import TYPE_CHECKING, Literal

from butler.transport.content_sanitize import sanitize_stream_delta, strip_think_blocks

if TYPE_CHECKING:
    from rich.console import Console

StreamMode = Literal["live", "buffer"]


def _resolve_stream_mode(mode: str | None) -> StreamMode:
    raw = (mode or os.getenv("BUTLER_CLI_STREAM_MODE") or "live").strip().lower()
    return "buffer" if raw == "buffer" else "live"


class StreamRenderer:
    """Streams assistant text: live line printing or end-of-turn buffer only."""

    def __init__(
        self,
        console: "Console | None" = None,
        *,
        title: str = "Butler",
        mode: str | None = None,
    ) -> None:
        self._console = console
        self._title = title
        self._mode = _resolve_stream_mode(mode)
        self._buffer = ""
        self._line_buf = ""
        self._box_open = False
        self._streamed_live = False
        self._lines_emitted = 0

    @property
    def text(self) -> str:
        return self._buffer

    @property
    def streamed_live(self) -> bool:
        return self._streamed_live

    @property
    def lines_emitted(self) -> int:
        return self._lines_emitted

    def had_body(self) -> bool:
        return bool(self._buffer.strip())

    def on_delta(self, delta: str | None) -> None:
        if delta is None:
            self.on_boundary()
            return
        if not delta:
            return
        cleaned = sanitize_stream_delta(delta)
        if not cleaned:
            return
        self._buffer += cleaned
        if self._mode == "buffer":
            return
        self._streamed_live = True
        self._line_buf += cleaned
        self._emit_complete_lines()

    def on_boundary(self) -> None:
        """Tool batch / iteration boundary — flush partial line and close stream box."""
        if self._mode == "buffer":
            return
        self._flush_partial_line()
        self._close_box()

    def flush(self) -> None:
        """End of user turn — emit trailing text and close box."""
        if self._mode == "buffer":
            return
        self._flush_partial_line()
        self._close_box()

    def close(self) -> None:
        self.flush()

    def _wrap_width(self) -> int:
        return max(shutil.get_terminal_size((80, 24)).columns - 6, 24)

    def _emit_complete_lines(self) -> None:
        width = self._wrap_width()
        while "\n" in self._line_buf:
            line, self._line_buf = self._line_buf.split("\n", 1)
            self._emit_line(line)
        while len(self._line_buf) > width:
            chunk = self._line_buf[:width]
            self._line_buf = self._line_buf[width:]
            self._emit_line(chunk)

    def _flush_partial_line(self) -> None:
        if not self._line_buf:
            return
        self._emit_line(self._line_buf)
        self._line_buf = ""

    def _emit_line(self, line: str) -> None:
        if not self._console:
            return
        visible = strip_think_blocks(line).strip("\r")
        if not visible.strip():
            return
        self._open_box()
        self._console.print(f"│ {visible}", highlight=False)
        self._lines_emitted += 1

    def _open_box(self) -> None:
        if self._box_open or not self._console:
            return
        self._box_open = True
        width = shutil.get_terminal_size((80, 24)).columns
        label = f" {self._title} "
        fill = max(width - len(label) - 4, 0)
        header = f"╭{label}{'─' * fill}╮"
        self._console.print(f"[cyan]{header}[/cyan]", highlight=False)

    def _close_box(self) -> None:
        if not self._box_open or not self._console:
            return
        width = shutil.get_terminal_size((80, 24)).columns
        self._console.print(f"[cyan]{'╰' + '─' * max(width - 2, 0) + '╯'}[/cyan]", highlight=False)
        self._box_open = False

"""Line-buffered streaming output with optional box chrome."""

from __future__ import annotations

from typing import TYPE_CHECKING

from butler.transport.content_sanitize import sanitize_stream_delta

if TYPE_CHECKING:
    from rich.console import Console

_ACCENT = "cyan"


class StreamRenderer:
    """Buffers stream tokens, prints line-by-line inside a light box."""

    def __init__(self, console: "Console", *, title: str = "Butler") -> None:
        self._console = console
        self._title = title
        self._open = False
        self._line_buf = ""
        self._full_text: list[str] = []

    @property
    def text(self) -> str:
        return "".join(self._full_text) + self._line_buf

    def _open_box(self) -> None:
        if self._open:
            return
        self._open = True
        label = self._title
        pad = max(0, 48 - len(label))
        self._console.print(f"[{_ACCENT}]╭─ {label} ─{'─' * pad}[/{_ACCENT}]")

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
            self._console.print(f"[{_ACCENT}]│[/{_ACCENT}] {line}", highlight=False)

    def close(self) -> None:
        if not self._open:
            if self._line_buf:
                self._full_text.append(self._line_buf)
                self._line_buf = ""
            return
        if self._line_buf:
            self._console.print(f"[{_ACCENT}]│[/{_ACCENT}] {self._line_buf}", highlight=False)
            self._full_text.append(self._line_buf)
            self._line_buf = ""
        self._console.print(f"[{_ACCENT}]╰{'─' * 52}[/{_ACCENT}]")
        self._open = False

    def render_final_markdown(self) -> None:
        """Re-render accumulated text as Markdown when streaming used."""
        from rich.markdown import Markdown

        body = self.text.strip()
        if not body:
            return
        self._console.print()
        self._console.print(Markdown(body))

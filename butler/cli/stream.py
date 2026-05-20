"""Line-buffered streaming output with optional box chrome."""

from __future__ import annotations

from typing import TYPE_CHECKING

from butler.transport.content_sanitize import sanitize_stream_delta

if TYPE_CHECKING:
    from rich.console import Console


class StreamRenderer:
    """Buffers assistant stream text; rendered via Rich in ``finish_turn``."""

    def __init__(
        self,
        console: "Console | None" = None,
        *,
        title: str = "Butler",
    ) -> None:
        self._console = console
        self._title = title
        self._buffer = ""

    @property
    def text(self) -> str:
        return self._buffer

    def had_body(self) -> bool:
        return bool(self._buffer.strip())

    def on_delta(self, delta: str | None) -> None:
        if delta is None:
            return
        if not delta:
            return
        cleaned = sanitize_stream_delta(delta)
        if cleaned:
            self._buffer += cleaned

    def close(self) -> None:
        return

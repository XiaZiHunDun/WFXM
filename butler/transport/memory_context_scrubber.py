"""Strip injected <memory-context> blocks from streamed LLM deltas (Hermes subset)."""

from __future__ import annotations

import os
import re

_BLOCK = re.compile(
    r"<memory-context\b[^>]*>.*?</memory-context\s*>",
    re.IGNORECASE | re.DOTALL,
)
_TAG = "<memory-context"
_CLOSE = "</memory-context>"


def memory_stream_scrub_enabled() -> bool:
    raw = os.getenv("BUTLER_STREAM_MEMORY_SCRUB", "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def _hold_index(buf: str) -> int:
    """Index where an incomplete memory-context block starts, or -1."""
    lower = buf.lower()
    for plen in range(len(_TAG) - 1, 0, -1):
        partial = _TAG[:plen]
        if lower.endswith(partial):
            return len(buf) - plen
    pos = lower.find(_TAG)
    if pos < 0:
        return -1
    if pos > 0 and buf[pos - 1] == "/":
        return -1
    if _CLOSE.lower() not in lower[pos:]:
        return pos
    return -1


class StreamingMemoryContextScrubber:
    """Buffer streamed text and drop memory-context blocks (including partial tags)."""

    def __init__(self) -> None:
        self._buf = ""

    def reset(self) -> None:
        self._buf = ""

    def feed(self, chunk: str) -> str:
        if not chunk:
            return ""
        self._buf += chunk
        while True:
            m = _BLOCK.search(self._buf)
            if not m:
                break
            self._buf = self._buf[: m.start()] + self._buf[m.end() :]
        hold = _hold_index(self._buf)
        if hold >= 0:
            out = self._buf[:hold]
            self._buf = self._buf[hold:]
            return out
        out = self._buf
        self._buf = ""
        return out


def scrub_stream_delta(chunk: str, scrubber: StreamingMemoryContextScrubber | None) -> str:
    if not memory_stream_scrub_enabled() or not chunk:
        return chunk
    if scrubber is None:
        return chunk
    return scrubber.feed(chunk)

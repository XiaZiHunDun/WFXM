"""Streaming tool dispatch best-effort helpers (P0-A)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from butler.core.best_effort import safe_best_effort


def dispatch_streaming_tool_ready_safe(
    on_tool_call_ready: Callable[[int, str, str, dict[str, Any]], None],
    *,
    idx: int,
    tool_id: str,
    name: str,
    args: dict[str, Any],
) -> None:
    def _run() -> None:
        on_tool_call_ready(idx, tool_id, name, args)

    safe_best_effort(_run, label="streaming_tools.dispatch", default=None)

"""Streaming tool callback best-effort helpers (P0-A)."""

from __future__ import annotations

import logging
from typing import Any, Callable

from butler.core.best_effort import safe_best_effort

logger = logging.getLogger(__name__)


def invoke_streaming_tool_callback_safe(
    callback: Callable[..., Any],
    idx: int,
    tool_id: str,
    name: str,
    args: dict[str, Any],
) -> None:
    def _run() -> None:
        callback(idx, tool_id, name, args)

    safe_best_effort(
        _run,
        label=f"streaming_signal.dispatch.{name}",
        default=None,
    )

"""Truncate tool batch at finish-style tools (OpenHands subset)."""

from __future__ import annotations

from butler.env_parse import env_truthy
from butler.transport.types import ToolCall

_FINISH_NAMES = frozenset(
    {
        "finish",
        "finish_task",
        "task_complete",
        "complete_task",
        "submit_result",
    }
)


def finish_tool_truncate_enabled() -> bool:
    return env_truthy("BUTLER_FINISH_TOOL_TRUNCATE", default=True)


def truncate_tool_calls_at_finish(tool_calls: list[ToolCall]) -> list[ToolCall]:
    if not finish_tool_truncate_enabled() or not tool_calls:
        return tool_calls
    out: list[ToolCall] = []
    for tc in tool_calls:
        out.append(tc)
        if (tc.name or "").strip().lower() in _FINISH_NAMES:
            break
    return out


__all__ = ["finish_tool_truncate_enabled", "truncate_tool_calls_at_finish"]

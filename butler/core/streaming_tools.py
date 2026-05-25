"""Dispatch read-only tools as soon as streamed tool arguments are complete."""

from __future__ import annotations

import json
import logging
from typing import Any, Callable

from butler.env_parse import env_truthy

logger = logging.getLogger(__name__)

STREAMING_TOOL_NAMES = frozenset({
    "read_file",
    "grep",
    "search_files",
    "list_directory",
    "glob",
    "list_dir",
})


def streaming_tools_enabled() -> bool:
    return env_truthy("BUTLER_STREAMING_TOOLS", default=True)


def is_streaming_tool(name: str) -> bool:
    n = (name or "").strip().lower()
    if n in STREAMING_TOOL_NAMES:
        return True
    return n.startswith(("read_", "search_", "grep"))


def batch_eligible_for_streaming(tool_calls: list[Any]) -> bool:
    if not tool_calls or not streaming_tools_enabled():
        return False
    names = []
    for tc in tool_calls:
        names.append(getattr(tc, "name", "") or "")
    return all(is_streaming_tool(n) for n in names if n)


def try_parse_tool_arguments(args_str: str) -> dict[str, Any] | None:
    text = (args_str or "").strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
    except (TypeError, json.JSONDecodeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def notify_complete_tool_calls_from_stream(
    collected: dict[int, dict[str, Any]],
    on_tool_call_ready: Callable[[int, str, str, dict], None] | None,
) -> None:
    """Invoke callback for each tool call whose arguments JSON is complete (once)."""
    if not on_tool_call_ready or not streaming_tools_enabled():
        return
    for idx in sorted(collected.keys()):
        entry = collected[idx]
        if entry.get("_stream_dispatched"):
            continue
        name = str(entry.get("name") or "").strip()
        if not is_streaming_tool(name):
            continue
        args = try_parse_tool_arguments(str(entry.get("arguments") or ""))
        if args is None:
            continue
        entry["_stream_dispatched"] = True
        tool_id = str(entry.get("id") or f"call_{idx}")
        try:
            on_tool_call_ready(idx, tool_id, name, args)
        except Exception as exc:
            logger.debug("Streaming tool dispatch skipped %s: %s", name, exc)

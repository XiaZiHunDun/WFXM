"""Transport-level streaming-signal dispatch.

This module replaces the former ``butler.core.streaming_tools`` dependency
that ``butler/transport/llm_client.py`` had at lines 360, 383, 476. The
audit (``docs/reviews/project-deep-audit-2026-06-r1to8.md`` §R1-1)
classified that reach as a layering violation: ``transport/`` is the
lowest layer of the v4 architecture and must not import from ``core/``.

The dispatch logic itself is pure (it inspects a collected tool-call dict
and fires a callback once per complete, streaming-eligible call), so it
lives naturally in transport. The helpers here intentionally mirror the
ones still used by ``butler.core.streaming_tools`` for core-side concerns
(``batch_eligible_for_streaming`` etc.) — they are small, self-contained,
and keep the layering boundary clean.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable

from butler.env_parse import env_truthy

logger = logging.getLogger(__name__)

_STREAMING_TOOL_NAMES = frozenset({
    "read_file",
    "grep",
    "search_files",
    "list_directory",
    "glob",
    "list_dir",
})


def _streaming_tools_enabled() -> bool:
    return env_truthy("BUTLER_STREAMING_TOOLS", default=True)


def _is_streaming_tool(name: str) -> bool:
    n = (name or "").strip().lower()
    if n in _STREAMING_TOOL_NAMES:
        return True
    return n.startswith(("read_", "search_", "grep"))


def _try_parse_tool_arguments(args_str: str) -> dict[str, Any] | None:
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
    """Invoke ``on_tool_call_ready`` for each tool call whose JSON args are complete (once).

    Mirrors the contract of the former core-side implementation so callers
    in ``llm_client.py`` do not need to know which layer hosts the helper.
    """
    if not on_tool_call_ready or not _streaming_tools_enabled():
        return
    for idx in sorted(collected.keys()):
        entry = collected[idx]
        if entry.get("_stream_dispatched"):
            continue
        name = str(entry.get("name") or "").strip()
        if not _is_streaming_tool(name):
            continue
        args = _try_parse_tool_arguments(str(entry.get("arguments") or ""))
        if args is None:
            continue
        entry["_stream_dispatched"] = True
        tool_id = str(entry.get("id") or f"call_{idx}")
        from butler.transport.streaming_signal_ops import invoke_streaming_tool_callback_safe

        invoke_streaming_tool_callback_safe(on_tool_call_ready, idx, tool_id, name, args)

"""H1: optional one-line turn tool summary for WeChat (WS-H)."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_READ_TOOLS = frozenset({"read_file"})
_LOCAL_SEARCH_TOOLS = frozenset({"grep", "search_files", "glob"})
_NETWORK_SEARCH_TOOLS = frozenset({"web_search"})
_DELEGATE_TOOLS = frozenset({"delegate_task"})
_MEMORY_TOOLS = frozenset({"butler_recall", "butler_remember"})
_RUN_TOOLS = frozenset({"run_terminal", "run_runtime_job"})


def _is_network_search_tool(tool: str) -> bool:
    """Count DuckDuckGo web_search and Firecrawl MCP search tools."""
    name = str(tool or "").strip().lower()
    if name in _NETWORK_SEARCH_TOOLS:
        return True
    return "firecrawl" in name and "search" in name


def turn_summary_enabled() -> bool:
    return os.getenv("BUTLER_TURN_SUMMARY_LINE", "0").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def turn_summary_min_out_chars() -> int:
    try:
        return max(0, int(os.getenv("BUTLER_TURN_SUMMARY_MIN_CHARS", "400")))
    except ValueError:
        return 400


def _parse_args(raw: str) -> dict[str, Any]:
    text = str(raw or "").strip()
    if not text:
        return {}
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _epoch_tool_actions(session_key: str) -> list[dict[str, Any]]:
    sk = str(session_key or "").strip()
    if not sk:
        return []
    try:
        from butler.core.session_epoch import load_epoch_transcript_rows
    except Exception as exc:
        logger.debug("turn summary load skipped: %s", exc)
        return []
    rows = load_epoch_transcript_rows(sk, max_lines=500)
    return [r for r in rows if str(r.get("type") or "") == "tool_action"]


def build_turn_summary_line(session_key: str) -> str | None:
    """Compact Chinese summary like ``读了3文件·检索1次·无委派``."""
    actions = _epoch_tool_actions(session_key)
    if not actions:
        return None

    read_paths: set[str] = set()
    search_n = 0
    delegate_n = 0
    memory_n = 0
    run_n = 0

    for row in actions:
        tool = str(row.get("tool") or "").strip().lower()
        if tool in _READ_TOOLS:
            args = _parse_args(str(row.get("args_preview") or ""))
            path = str(args.get("path") or "").strip()
            if path:
                read_paths.add(path)
        elif tool in _LOCAL_SEARCH_TOOLS or _is_network_search_tool(tool):
            search_n += 1
        elif tool in _DELEGATE_TOOLS:
            delegate_n += 1
        elif tool in _MEMORY_TOOLS:
            memory_n += 1
        elif tool in _RUN_TOOLS:
            run_n += 1

    parts: list[str] = []
    if read_paths:
        parts.append(f"读了{len(read_paths)}文件")
    if search_n:
        parts.append(f"检索{search_n}次")
    if delegate_n:
        parts.append(f"委派{delegate_n}次")
    elif not delegate_n and (read_paths or search_n or memory_n or run_n):
        parts.append("无委派")
    if memory_n:
        parts.append(f"记忆{memory_n}次")
    if run_n:
        parts.append(f"命令{run_n}次")

    if not parts:
        return None
    return "·".join(parts)


def maybe_prepend_turn_summary(session_key: str, out_text: str) -> str:
    """Prepend summary when opt-in env is set and reply is long enough."""
    if not turn_summary_enabled():
        return out_text
    out = str(out_text or "")
    if len(out) < turn_summary_min_out_chars():
        return out
    line = build_turn_summary_line(session_key)
    if not line:
        return out
    return f"📎 {line}\n\n{out}"


__all__ = [
    "build_turn_summary_line",
    "maybe_prepend_turn_summary",
    "turn_summary_enabled",
    "turn_summary_min_out_chars",
]

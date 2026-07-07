"""Inline compression of old tool messages in context (claude-mem / 主线 F P2)."""

from __future__ import annotations

import os
from typing import Any

from butler.env_parse import env_truthy, int_env


def inline_tool_compress_enabled() -> bool:
    return bool(env_truthy("BUTLER_INLINE_TOOL_COMPRESS", default=False))


def _max_tool_chars() -> int:
    try:
        return int(int_env("BUTLER_INLINE_TOOL_COMPRESS_MAX_CHARS", 1200, min=50))
    except ValueError:
        return 1200


def _keep_tail_tool_messages() -> int:
    try:
        return int(int_env("BUTLER_INLINE_TOOL_COMPRESS_KEEP", 6, min=2))
    except ValueError:
        return 6


def compress_inline_tool_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Truncate content on older tool role messages (experimental)."""
    if not inline_tool_compress_enabled() or not messages:
        return messages
    tool_indices = [i for i, m in enumerate(messages) if m.get("role") == "tool"]
    if len(tool_indices) <= _keep_tail_tool_messages():
        return messages
    drop = set(tool_indices[: -_keep_tail_tool_messages()])
    max_chars = _max_tool_chars()
    out: list[dict[str, Any]] = []
    for i, msg in enumerate(messages):
        if i not in drop:
            out.append(msg)
            continue
        copy = dict(msg)
        content = str(copy.get("content") or "")
        if len(content) > max_chars:
            copy["content"] = content[:max_chars] + "\n…[inline_tool_compress]"
        out.append(copy)
    return out


__all__ = ["compress_inline_tool_messages", "inline_tool_compress_enabled"]

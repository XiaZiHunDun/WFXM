"""Backward tool-output pruning (OpenCode SessionCompaction.prune subset)."""

from __future__ import annotations

from typing import Any

from butler.context_settings import ToolPruneSettings
from butler.core.tool_prune_policy import (
    CLEARED_TOOL_RESULT_MESSAGE,
    classify_tool,
    is_persisted_tool_result,
)

_PRUNE_PROTECTED_TOOLS = frozenset({"skill_view", "skills_list"})


def _tool_prune_settings() -> ToolPruneSettings:
    from butler.context_settings import resolve_context_config

    return resolve_context_config().tool_prune


def prune_minimum_chars() -> int:
    return int(_tool_prune_settings().backward_minimum)


def clear_at_least_chars() -> int:
    """LangChain ClearToolUsesEdit-style floor (alias for minimum by default)."""
    return int(_tool_prune_settings().backward_minimum)


def prune_protect_chars() -> int:
    return int(_tool_prune_settings().backward_protect)


def backward_prune_tool_outputs(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Erase older tool message bodies when prunable volume exceeds minimum."""
    if not _tool_prune_settings().backward_enabled:
        return messages

    tool_idxs = [i for i, m in enumerate(messages) if m.get("role") == "tool"]
    if len(tool_idxs) < 2:
        return messages

    minimum = clear_at_least_chars()
    protect = prune_protect_chars()
    total = 0
    pruned = 0
    to_clear: list[int] = []
    user_turns = 0

    for msg_index in range(len(messages) - 1, -1, -1):
        msg = messages[msg_index]
        if msg.get("role") == "user":
            user_turns += 1
        if user_turns < 2:
            continue
        if msg.get("role") == "assistant":
            content = str(msg.get("content") or "")
            if "[CONTEXT COMPACTION" in content or "## Goal" in content[:200]:
                break

        if msg.get("role") != "tool":
            continue
        idx = msg_index
        content = str(msg.get("content") or "")
        if is_persisted_tool_result(content):
            continue
        tool_name = ""
        for j in range(idx - 1, -1, -1):
            prev = messages[j]
            if prev.get("role") != "assistant":
                continue
            for tc in prev.get("tool_calls") or []:
                fn = tc.get("function") or {}
                if str(tc.get("id") or "") == str(msg.get("tool_call_id") or ""):
                    tool_name = str(fn.get("name") or "")
                    break
            break
        if tool_name in _PRUNE_PROTECTED_TOOLS or classify_tool(tool_name) == "preserve":
            continue
        if content.strip() in (CLEARED_TOOL_RESULT_MESSAGE, "[旧工具结果已清空]"):
            break
        est = max(1, len(content) // 4)
        total += est
        if total <= protect:
            continue
        pruned += est
        to_clear.append(idx)

    if pruned < minimum and to_clear:
        extra: list[int] = []
        for idx in tool_idxs:
            if idx in to_clear:
                continue
            msg = messages[idx]
            content = str(msg.get("content") or "")
            if content.strip() in (CLEARED_TOOL_RESULT_MESSAGE, "[旧工具结果已清空]"):
                continue
            if is_persisted_tool_result(content):
                continue
            extra.append(idx)
            pruned += max(1, len(content) // 4)
            if pruned >= minimum:
                break
        to_clear.extend(extra)

    if pruned < minimum:
        return messages

    out = [dict(m) for m in messages]
    for idx in to_clear:
        out[idx] = {**out[idx], "content": CLEARED_TOOL_RESULT_MESSAGE}
    return out

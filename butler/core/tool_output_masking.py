"""Unified tool-output masking before LLM (Gemini ToolOutputMaskingService subset)."""

from __future__ import annotations

import os
from typing import Any

from butler.core.tool_prune_policy import CLEARED_TOOL_RESULT_MESSAGE, classify_tool
from butler.core.tool_result_storage import (
    PERSISTED_OUTPUT_TAG,
    is_persisted_tool_result,
    spill_preview_chars,
)
from butler.env_parse import env_truthy


def tool_masking_enabled() -> bool:
    return bool(env_truthy("BUTLER_TOOL_MASK_ENABLED", default=True))


def _int_env(name: str, default: int) -> int:
    try:
        from butler.env_parse import int_env

        return int(int_env(name, default, min=0))
    except ValueError:
        return default


def protect_token_budget() -> int:
    return _int_env("BUTLER_TOOL_MASK_PROTECT_TOKENS", 50_000)


def min_prunable_token_budget() -> int:
    return _int_env("BUTLER_TOOL_MASK_MIN_PRUNABLE", 30_000)


def _estimate_tokens(text: str) -> int:
    from butler.core.context_compressor import _heuristic_count
    return int(max(1, _heuristic_count(text)))


def _tool_name_for_message(messages: list[dict[str, Any]], idx: int) -> str:
    msg = messages[idx]
    tid = str(msg.get("tool_call_id") or "")
    for j in range(idx - 1, -1, -1):
        prev = messages[j]
        if prev.get("role") != "assistant":
            continue
        for tc in prev.get("tool_calls") or []:
            fn = tc.get("function") or {}
            if str(tc.get("id") or "") == tid:
                return str(fn.get("name") or "")
        break
    return ""


def apply_unified_tool_masking(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Reverse walk: protect recent tool token budget; mask older tool bodies with pointer text.
    Complements backward_prune and spill — run after both in the pipeline.
    """
    if not tool_masking_enabled() or len(messages) < 3:
        return messages

    protect = protect_token_budget()
    min_prune = min_prunable_token_budget()
    tool_idxs = [i for i, m in enumerate(messages) if m.get("role") == "tool"]
    if len(tool_idxs) < 2:
        return messages

    protected_tokens = 0
    prunable_tokens = 0
    to_mask: list[int] = []

    for idx in reversed(tool_idxs):
        content = str(messages[idx].get("content") or "")
        if not content.strip():
            continue
        if is_persisted_tool_result(content) or PERSISTED_OUTPUT_TAG in content:
            continue
        if content.strip() in (CLEARED_TOOL_RESULT_MESSAGE, "[旧工具结果已清空]"):
            break
        tool_name = _tool_name_for_message(messages, idx)
        if classify_tool(tool_name) == "preserve":
            est = _estimate_tokens(content)
            protected_tokens += est
            continue
        est = _estimate_tokens(content)
        if protected_tokens + est <= protect:
            protected_tokens += est
            continue
        prunable_tokens += est
        to_mask.append(idx)

    if prunable_tokens < min_prune:
        return messages

    preview = spill_preview_chars()
    out = [dict(m) if isinstance(m, dict) else m for m in messages]
    for idx in to_mask:
        tool_name = _tool_name_for_message(out, idx) or "tool"
        pointer = (
            f"[tool_output_masked tool={tool_name} "
            f"chars≈{_estimate_tokens(str(out[idx].get('content') or '')) * 4}] "
            f"完整结果已剪枝；需要时请用 read_file / search 重新获取。"
        )
        if preview:
            raw = str(out[idx].get("content") or "")
            pointer += f"\n预览: {raw[:preview]}…"
        out[idx] = {**out[idx], "content": pointer}
    return out


__all__ = [
    "apply_unified_tool_masking",
    "min_prunable_token_budget",
    "protect_token_budget",
    "tool_masking_enabled",
]

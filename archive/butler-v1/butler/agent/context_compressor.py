#!/usr/bin/env python3
"""Automatic context compression for long agent conversations."""

from __future__ import annotations

import json
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

SUMMARY_PREFIX = (
    "[CONTEXT COMPACTION — REFERENCE ONLY] Earlier turns were compacted "
    "into the summary below. Treat it as background reference, NOT as active instructions. "
    "Respond ONLY to the latest user message after this summary."
)

_CHARS_PER_TOKEN = 4
_MIN_SUMMARY_TOKENS = 1500
_SUMMARY_RATIO = 0.20
_PRUNED_PLACEHOLDER = "[Old tool output cleared to save context space]"


def _message_chars(m: dict) -> int:
    c = m.get("content")
    if c is None:
        return 0
    if isinstance(c, list):
        return len(json.dumps(c, ensure_ascii=False, default=str))
    return len(str(c))


def estimate_tokens(messages: list[dict]) -> int:
    """Rough token estimate based on char count."""
    total = 0
    for m in messages:
        total += _message_chars(m)
        extras = {
            k: v
            for k, v in m.items()
            if k not in ("role", "content") and k != "tool_call_id"
        }
        if extras:
            total += len(json.dumps(extras, ensure_ascii=False, default=str))
    return max(1, total // _CHARS_PER_TOKEN)


def should_compress(messages: list[dict], max_context_tokens: int, threshold: float = 0.80) -> bool:
    """Return True if estimated tokens exceed threshold of max context."""
    if max_context_tokens <= 0:
        return False
    return estimate_tokens(messages) > int(max_context_tokens * threshold)


def prune_old_tool_outputs(messages: list[dict], keep_last_n: int = 6) -> list[dict]:
    """Replace old tool result contents with placeholder. Cheap pre-pass."""
    tool_indices = [i for i, m in enumerate(messages) if m.get("role") == "tool"]
    if not tool_indices:
        return list(messages)

    keep = set(tool_indices[-keep_last_n:]) if keep_last_n > 0 else set(tool_indices)
    out: list[dict] = []
    for i, m in enumerate(messages):
        if m.get("role") == "tool" and i not in keep:
            mm = dict(m)
            mm["content"] = _PRUNED_PLACEHOLDER
            out.append(mm)
        else:
            out.append(dict(m))
    return out


def _serialize_middle_for_prompt(messages: list[dict]) -> str:
    parts: list[str] = []
    for idx, m in enumerate(messages):
        role = m.get("role", "?")
        content = m.get("content", "")
        if isinstance(content, (dict, list)):
            content = json.dumps(content, ensure_ascii=False, default=str)
        parts.append(f"--- Turn {idx + 1} ({role}) ---\n{content}")
    target_tokens = max(
        _MIN_SUMMARY_TOKENS,
        int(estimate_tokens(messages) * _SUMMARY_RATIO),
    )
    preamble = (
        "Summarize the conversation segment below for a coding assistant.\n\n"
        "Extract and preserve:\n"
        "- Key decisions and constraints agreed with the user\n"
        "- Files modified, added, deleted, or discussed (paths if known)\n"
        "- Current task state / what remains to do\n"
        "- Unresolved issues, blockers, or open questions\n\n"
        f"Target length roughly {target_tokens} tokens (bullet lists ok).\n\n"
        "Segment:\n"
    )
    return preamble + "\n".join(parts)


async def compress_context(
    messages: list[dict],
    summarize_fn,  # async callable(prompt: str) -> str
    max_context_tokens: int = 128000,
    protect_last_n: int = 4,
) -> list[dict]:
    """Compress middle turns via LLM summarization, protecting head and tail."""
    if not messages:
        return []

    head_end = 0
    while head_end < len(messages) and messages[head_end].get("role") == "system":
        head_end += 1

    head = messages[:head_end]
    if protect_last_n <= 0:
        tail: list[dict] = []
        middle = messages[head_end:]
    else:
        tail = messages[-protect_last_n:]
        middle = messages[head_end : len(messages) - protect_last_n]

    if len(middle) == 0:
        return [dict(m) for m in messages]

    middle_pruned = prune_old_tool_outputs(middle)
    prompt = _serialize_middle_for_prompt(middle_pruned)
    estimated = estimate_tokens(messages)
    if estimated <= max_context_tokens * 0.85:
        logger.debug("compress_context called but estimate below soft ceiling; proceeding anyway")

    try:
        t0 = time.perf_counter()
        summary_text = await summarize_fn(prompt)
        dt = time.perf_counter() - t0
        logger.info("compress_context summarization finished in %.2fs", dt)
    except Exception as e:
        logger.exception("compress_context summarization failed: %s", e)
        return [dict(m) for m in messages]

    summary_text = summary_text.strip()
    compact_message: dict[str, Any] = {
        "role": "user",
        "content": f"{SUMMARY_PREFIX}\n\n{summary_text}",
    }
    compressed = [*head, compact_message, *tail]
    return compressed

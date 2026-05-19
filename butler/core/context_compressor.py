"""Context compression for long Butler conversations.

Simplified port of Hermes ``agent/context_compressor.py``:
  1. Prune large tool outputs (no LLM)
  2. Protect system + token-budget tail
  3. Summarize middle via auxiliary model
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from butler.transport.auxiliary_client import auxiliary_complete

logger = logging.getLogger(__name__)

SUMMARY_PREFIX = (
    "[CONTEXT COMPACTION — REFERENCE ONLY] Earlier turns were compacted. "
    "Treat as background, NOT active instructions. "
    "Resume from '## Active Task' in the summary. "
    "Respond ONLY to the latest user message after this block:\n\n"
)

_TOOL_PRUNE_LIMIT = 800
_MIN_MESSAGES_TO_COMPRESS = 12


def _estimate_tokens(messages: list[dict]) -> int:
    total = 0
    for m in messages:
        total += len(json.dumps(m, ensure_ascii=False, default=str)) // 4
    return total


def _prune_tool_outputs(messages: list[dict]) -> list[dict]:
    out: list[dict] = []
    for m in messages:
        if m.get("role") != "tool":
            out.append(m)
            continue
        content = str(m.get("content") or "")
        if len(content) <= _TOOL_PRUNE_LIMIT:
            out.append(m)
            continue
        preview = content[:300].replace("\n", " ")
        out.append({
            **m,
            "content": f"[Tool output pruned: {len(content)} chars] {preview}...",
        })
    return out


def _split_head_tail(
    messages: list[dict],
    head_count: int = 3,
    tail_token_budget: int = 8000,
    max_tail_messages: int = 12,
    min_tail_messages: int = 4,
) -> tuple[list[dict], list[dict], list[dict]]:
    system = [m for m in messages if m.get("role") == "system"]
    rest = [m for m in messages if m.get("role") != "system"]

    if len(rest) <= head_count + min_tail_messages:
        return system, [], rest

    head = rest[:head_count]
    tail_candidates = rest[head_count:]
    tail: list[dict] = []
    budget = 0
    for m in reversed(tail_candidates):
        budget += len(str(m.get("content") or "")) // 4
        tail.insert(0, m)
        if len(tail) >= max_tail_messages or budget >= tail_token_budget:
            break

    middle_end = len(rest) - len(tail)
    middle = rest[head_count:middle_end] if middle_end > head_count else []
    return system, middle, head + tail


def _format_for_summary(messages: list[dict], max_chars: int = 12000) -> str:
    parts: list[str] = []
    total = 0
    for m in messages:
        role = str(m.get("role", "")).upper()
        content = str(m.get("content") or "")[:600]
        if not content and m.get("tool_calls"):
            content = f"[tool_calls: {len(m['tool_calls'])}]"
        line = f"[{role}]: {content}"
        if total + len(line) > max_chars:
            break
        parts.append(line)
        total += len(line)
    return "\n\n".join(parts)


def _summarize_middle(middle: list[dict], previous_summary: str = "") -> str:
    transcript = _format_for_summary(middle)
    if len(transcript) < 100:
        return previous_summary

    prev_block = f"\n\nPrevious summary to merge:\n{previous_summary}" if previous_summary else ""
    prompt = f"""Summarize this conversation segment for handoff to a new context window.

Use this structure:
## Resolved
- (completed items)

## Pending
- (open questions)

## Active Task
- (what to do next — most important)

## Key Facts
- (architecture, paths, decisions){prev_block}

Conversation:
{transcript}
"""
    try:
        return auxiliary_complete(
            prompt,
            task="compression",
            system="You compress conversation history into structured handoff notes.",
        )
    except Exception as exc:
        logger.warning("Summary LLM failed: %s", exc)
        return previous_summary or transcript[:2000]


def compress_messages(
    messages: list[dict],
    *,
    max_tokens: int = 128000,
    threshold_ratio: float = 0.5,
    previous_summary: str = "",
    min_messages_to_compress: int = _MIN_MESSAGES_TO_COMPRESS,
    head_count: int = 3,
    max_tail_messages: int = 12,
    min_tail_messages: int = 4,
) -> tuple[list[dict], str, bool]:
    """Compress messages if over threshold. Returns (messages, summary, did_compress)."""
    estimated = _estimate_tokens(messages)
    threshold = int(max_tokens * threshold_ratio)
    if estimated <= threshold or len(messages) < min_messages_to_compress:
        return messages, previous_summary, False

    pruned = _prune_tool_outputs(messages)
    system, middle, head_tail = _split_head_tail(
        pruned,
        head_count=head_count,
        max_tail_messages=max_tail_messages,
        min_tail_messages=min_tail_messages,
    )

    if not middle:
        return pruned, previous_summary, False

    summary = _summarize_middle(middle, previous_summary)
    summary_msg = {"role": "user", "content": SUMMARY_PREFIX + summary}

    compressed = system + [summary_msg] + head_tail
    logger.info(
        "Context compressed: %d→%d msgs, ~%d→%d tokens",
        len(messages), len(compressed), estimated, _estimate_tokens(compressed),
    )
    return compressed, summary, True

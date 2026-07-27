"""Context compression enhancements.

Provides:
1. Key information extraction (decisions, errors, important results)
2. Smart message selection for preservation
3. Compression quality metrics
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

_DECISION_KEYWORDS = frozenset({
    "决定", "decision", "选择", "chose", "selected",
    "方案", "approach", "plan", "计划", "strategy",
})

_ERROR_KEYWORDS = frozenset({
    "error", "错误", "fail", "失败", "exception", "异常",
    "问题", "issue", "problem", "bug",
})

_RESULT_KEYWORDS = frozenset({
    "完成", "done", "完成", "finished", "成功", "success",
    "结果", "result", "output", "输出",
})


@dataclass
class MessageImportance:
    """Importance score for a message."""

    index: int
    role: str
    score: float = 0.0
    reasons: list[str] = field(default_factory=list)

    def add_reason(self, reason: str, weight: float = 1.0) -> None:
        self.reasons.append(reason)
        self.score += weight


def extract_key_information(
    messages: list[dict[str, Any]],
) -> list[MessageImportance]:
    """Extract key information from messages and score importance.

    Scoring factors:
    - Contains decision keywords: +2.0
    - Contains error keywords: +1.5
    - Contains result keywords: +1.0
    - Is a system message: +3.0
    - Contains code blocks: +0.5
    - Is the latest user message: +2.0
    - Is the latest assistant message: +1.5
    """
    results: list[MessageImportance] = []

    total = len(messages)
    for i, msg in enumerate(messages):
        role = msg.get("role", "")
        content = msg.get("content", "")
        if isinstance(content, list):
            content = " ".join(
                str(block.get("text", ""))
                for block in content
                if isinstance(block, dict)
            )
        content_str = str(content).lower()

        importance = MessageImportance(index=i, role=role)

        if role == "system":
            importance.add_reason("system_message", 3.0)

        if role == "user" and i == total - 1:
            importance.add_reason("latest_user", 2.0)
        elif role == "assistant" and i >= total - 2:
            importance.add_reason("recent_assistant", 1.5)

        for kw in _DECISION_KEYWORDS:
            if kw in content_str:
                importance.add_reason(f"decision_keyword:{kw}", 2.0)
                break

        for kw in _ERROR_KEYWORDS:
            if kw in content_str:
                importance.add_reason(f"error_keyword:{kw}", 1.5)
                break

        for kw in _RESULT_KEYWORDS:
            if kw in content_str:
                importance.add_reason(f"result_keyword:{kw}", 1.0)
                break

        if "```" in content_str:
            importance.add_reason("code_block", 0.5)

        results.append(importance)

    return results


def select_messages_for_preservation(
    messages: list[dict[str, Any]],
    max_preserve: int = 5,
    min_score: float = 1.0,
) -> list[int]:
    """Select message indices to preserve during compression.

    Returns indices of messages that should NOT be summarized.
    """
    importance_scores = extract_key_information(messages)

    scored = sorted(importance_scores, key=lambda x: x.score, reverse=True)

    preserved: list[int] = []
    for imp in scored:
        if len(preserved) >= max_preserve:
            break
        if imp.score >= min_score:
            preserved.append(imp.index)

    preserved.sort()
    return preserved


def build_compression_summary(
    messages: list[dict[str, Any]],
    preserved_indices: list[int],
    max_chars: int = 2000,
) -> str:
    """Build a summary of non-preserved messages."""
    summary_parts: list[str] = []

    prev_idx = -1
    for idx in preserved_indices:
        if idx > prev_idx + 1:
            segment = messages[prev_idx + 1 : idx]
            if segment:
                segment_summary = _summarize_segment(segment, max_chars // 2)
                if segment_summary:
                    summary_parts.append(f"[对话片段 {prev_idx + 1}-{idx - 1}]")
                    summary_parts.append(segment_summary)
        prev_idx = idx

    if prev_idx < len(messages) - 1:
        segment = messages[prev_idx + 1 :]
        if segment:
            segment_summary = _summarize_segment(segment, max_chars // 2)
            if segment_summary:
                summary_parts.append(f"[对话片段 {prev_idx + 1}-{len(messages) - 1}]")
                summary_parts.append(segment_summary)

    return "\n".join(summary_parts)[:max_chars]


def _summarize_segment(
    messages: list[dict[str, Any]],
    max_chars: int,
) -> str:
    """Summarize a segment of messages."""
    user_intents: list[str] = []
    assistant_actions: list[str] = []

    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if isinstance(content, list):
            content = " ".join(
                str(block.get("text", ""))
                for block in content
                if isinstance(block, dict)
            )
        content_str = str(content)

        if role == "user":
            user_intents.append(content_str[:100])
        elif role == "assistant":
            assistant_actions.append(content_str[:100])

    parts: list[str] = []
    if user_intents:
        parts.append("用户: " + "; ".join(user_intents[-3:]))
    if assistant_actions:
        parts.append("助手: " + "; ".join(assistant_actions[-3:]))

    return " | ".join(parts)[:max_chars]


def estimate_compression_ratio(
    original_tokens: int,
    summary_chars: int,
) -> float:
    """Estimate the compression ratio.

    Returns ratio of summary size to original size.
    """
    if original_tokens <= 0:
        return 0.0

    estimated_summary_tokens = summary_chars // 4
    return min(1.0, estimated_summary_tokens / original_tokens)


__all__ = [
    "MessageImportance",
    "extract_key_information",
    "select_messages_for_preservation",
    "build_compression_summary",
    "estimate_compression_ratio",
]
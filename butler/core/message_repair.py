"""Repair malformed message sequences before LLM API calls.

Ported from Hermes ``run_agent._repair_message_sequence`` (simplified).
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


def _content_str(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for p in content:
            if isinstance(p, dict) and p.get("type") == "text":
                parts.append(str(p.get("text", "")))
            else:
                parts.append(str(p))
        return "\n".join(parts)
    return str(content)


def repair_message_sequence(messages: list[dict]) -> tuple[list[dict], int]:
    """Drop orphan tool results and merge consecutive user messages.

    Returns (repaired_messages, repair_count).
    """
    if not messages:
        return [], 0

    repairs = 0
    known_tool_ids: set[str] = set()
    filtered: list[dict] = []

    for msg in messages:
        if not isinstance(msg, dict):
            filtered.append(msg)
            continue
        role = msg.get("role")
        if role == "assistant":
            known_tool_ids = set()
            for tc in msg.get("tool_calls") or []:
                if isinstance(tc, dict):
                    tc_id = tc.get("id")
                    if tc_id:
                        known_tool_ids.add(tc_id)
            filtered.append(msg)
        elif role == "tool":
            tc_id = msg.get("tool_call_id")
            if tc_id and tc_id in known_tool_ids:
                filtered.append(msg)
            else:
                repairs += 1
        else:
            if role == "user":
                known_tool_ids = set()
            filtered.append(msg)

    merged: list[dict] = []
    for msg in filtered:
        if (
            merged
            and isinstance(msg, dict)
            and msg.get("role") == "user"
            and isinstance(merged[-1], dict)
            and merged[-1].get("role") == "user"
        ):
            prev = merged[-1]
            prev_c = _content_str(prev.get("content"))
            new_c = _content_str(msg.get("content"))
            merged[-1] = {
                **prev,
                "content": f"{prev_c}\n\n{new_c}".strip() if prev_c and new_c else (prev_c or new_c),
            }
            repairs += 1
        else:
            merged.append(msg)

    if repairs:
        logger.debug("Message sequence repairs: %d", repairs)
    return merged, repairs


def repair_tool_arguments(messages: list[dict]) -> int:
    """Fix invalid JSON in assistant tool_call arguments."""
    from butler.core.json_repair import repair_tool_call_arguments

    fixes = 0
    for msg in messages:
        if msg.get("role") != "assistant":
            continue
        for tc in msg.get("tool_calls") or []:
            if not isinstance(tc, dict):
                continue
            fn = tc.get("function") or {}
            if not isinstance(fn, dict):
                continue
            raw = fn.get("arguments", "{}")
            if isinstance(raw, dict):
                continue
            raw_str = raw if isinstance(raw, str) else str(raw)
            try:
                json.loads(raw_str or "{}")
            except (json.JSONDecodeError, TypeError):
                name = fn.get("name", "?")
                repaired = repair_tool_call_arguments(raw_str, tool_name=name)
                if repaired != raw_str:
                    fn["arguments"] = repaired
                    fixes += 1
    return fixes

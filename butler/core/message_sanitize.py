"""API-bound message sanitization before LLM calls (Hermes run_agent L5837+)."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_VALID_ROLES = frozenset({"system", "user", "assistant", "tool"})
_STUB_TOOL_RESULT = "[Result unavailable — see context summary above]"


def _tool_call_id(tc: dict) -> str | None:
    if isinstance(tc, dict):
        return tc.get("id")
    return None


def _tool_call_name(tc: dict) -> str:
    if not isinstance(tc, dict):
        return "unknown"
    fn = tc.get("function") or {}
    if isinstance(fn, dict):
        return str(fn.get("name") or "unknown")
    return "unknown"


def is_thinking_only_assistant(msg: dict) -> bool:
    """Assistant turn with only reasoning, no text or tool_calls."""
    if msg.get("role") != "assistant":
        return False
    if msg.get("tool_calls"):
        return False
    content = msg.get("content")
    if isinstance(content, str) and content.strip():
        return False
    if isinstance(content, list):
        for block in content:
            if not isinstance(block, dict):
                if block:
                    return False
                continue
            btype = block.get("type")
            if btype in ("thinking", "redacted_thinking"):
                continue
            if btype == "text" and str(block.get("text", "")).strip():
                return False
            if btype not in ("thinking", "redacted_thinking", "text"):
                return False
    elif content not in (None, ""):
        return False
    reasoning = msg.get("reasoning_content") or msg.get("reasoning")
    if isinstance(reasoning, str) and reasoning.strip():
        return True
    rd = msg.get("reasoning_details")
    return isinstance(rd, list) and bool(rd)


def sanitize_api_messages(messages: list[dict]) -> tuple[list[dict], int]:
    """Role filter, orphan tool drop, stub missing tool results."""
    if not messages:
        return [], 0
    repairs = 0
    filtered = [m for m in messages if isinstance(m, dict) and m.get("role") in _VALID_ROLES]
    repairs += len(messages) - len(filtered)

    surviving: set[str] = set()
    for msg in filtered:
        if msg.get("role") == "assistant":
            for tc in msg.get("tool_calls") or []:
                cid = _tool_call_id(tc)
                if cid:
                    surviving.add(cid)

    result_ids: set[str] = set()
    for msg in filtered:
        if msg.get("role") == "tool":
            cid = msg.get("tool_call_id")
            if cid:
                result_ids.add(cid)

    orphaned = result_ids - surviving
    if orphaned:
        filtered = [
            m for m in filtered
            if not (m.get("role") == "tool" and m.get("tool_call_id") in orphaned)
        ]
        repairs += len(orphaned)

    missing = surviving - result_ids
    if missing:
        patched: list[dict] = []
        for msg in filtered:
            patched.append(msg)
            if msg.get("role") == "assistant":
                for tc in msg.get("tool_calls") or []:
                    cid = _tool_call_id(tc)
                    if cid in missing:
                        patched.append({
                            "role": "tool",
                            "name": _tool_call_name(tc),
                            "content": _STUB_TOOL_RESULT,
                            "tool_call_id": cid,
                        })
                        repairs += 1
        filtered = patched

    return filtered, repairs


def drop_thinking_only_assistants(messages: list[dict]) -> tuple[list[dict], int]:
    """Remove thinking-only assistant messages from API wire copy."""
    kept = [m for m in messages if not is_thinking_only_assistant(m)]
    dropped = len(messages) - len(kept)
    return kept, dropped


def sanitize_surrogates(text: str) -> str:
    """Remove lone UTF-16 surrogates that break JSON encoding."""
    if not text:
        return text
    return "".join(c for c in text if not (0xD800 <= ord(c) <= 0xDFFF))

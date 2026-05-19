"""Steer: inject user guidance into next tool result without interrupting (Hermes L5180+)."""

from __future__ import annotations

import logging
import threading
from typing import Any

logger = logging.getLogger(__name__)

_pending: str | None = None
_lock = threading.Lock()


def steer(text: str) -> bool:
    """Queue user text to append to the last tool result in the current batch."""
    global _pending
    cleaned = (text or "").strip()
    if not cleaned:
        return False
    with _lock:
        if _pending:
            _pending = _pending + "\n" + cleaned
        else:
            _pending = cleaned
    return True


def drain_steer() -> str | None:
    """Return and clear pending steer text."""
    global _pending
    with _lock:
        text = _pending
        _pending = None
    return text


def clear_steer() -> None:
    global _pending
    with _lock:
        _pending = None


def apply_steer_to_tool_results(messages: list[dict], num_tool_msgs: int) -> bool:
    """Append steer marker to the last tool message in the recent batch."""
    steer_text = drain_steer()
    if not steer_text or num_tool_msgs <= 0 or not messages:
        if steer_text:
            steer(steer_text)
        return False

    target_idx = None
    for j in range(len(messages) - 1, max(len(messages) - num_tool_msgs - 1, -1), -1):
        msg = messages[j]
        if isinstance(msg, dict) and msg.get("role") == "tool":
            target_idx = j
            break

    if target_idx is None:
        steer(steer_text)
        return False

    marker = f"\n\nUser guidance: {steer_text}"
    existing = messages[target_idx].get("content", "")
    if isinstance(existing, str):
        messages[target_idx]["content"] = existing + marker
    else:
        messages[target_idx]["content"] = str(existing) + marker
    logger.info("Applied steer (%d chars) to tool result", len(steer_text))
    return True

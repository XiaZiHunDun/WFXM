"""Steer: inject user guidance into next tool result without interrupting."""

from __future__ import annotations

import logging
import threading
from typing import Any, cast

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_pending_by_session: dict[str, str] = {}
_run_depth: dict[str, int] = {}


def _resolve_session_key(session_key: str | None = None) -> str:
    if session_key is not None and str(session_key).strip():
        return str(session_key).strip()
    from butler.core.steer_ops import resolve_session_key_from_context_safe

    sk = resolve_session_key_from_context_safe()
    if sk:
        return str(sk)
    return "default"


def mark_run_active(session_key: str) -> None:
    """Called when an AgentLoop turn starts (gateway or CLI)."""
    key = _resolve_session_key(session_key)
    with _lock:
        _run_depth[key] = _run_depth.get(key, 0) + 1


def mark_run_inactive(session_key: str) -> None:
    """Called when an AgentLoop turn finishes."""
    key = _resolve_session_key(session_key)
    with _lock:
        depth = _run_depth.get(key, 0) - 1
        if depth <= 0:
            _run_depth.pop(key, None)
        else:
            _run_depth[key] = depth


def is_run_active(session_key: str | None = None) -> bool:
    key = _resolve_session_key(session_key)
    with _lock:
        return _run_depth.get(key, 0) > 0


def steer(text: str, *, session_key: str | None = None) -> bool:
    """Queue user text to append to the last tool result in the current batch."""
    key = _resolve_session_key(session_key)
    cleaned = (text or "").strip()
    if not cleaned:
        return False
    with _lock:
        prev = _pending_by_session.get(key)
        if prev:
            _pending_by_session[key] = prev + "\n" + cleaned
        else:
            _pending_by_session[key] = cleaned
    return True


def drain_steer(session_key: str | None = None) -> str | None:
    """Return and clear pending steer text for a session."""
    key = _resolve_session_key(session_key)
    with _lock:
        text = _pending_by_session.pop(key, None)
    return text


def clear_steer(session_key: str | None = None) -> None:
    """Drop pending steer for one session (new turn boundary)."""
    key = _resolve_session_key(session_key)
    with _lock:
        _pending_by_session.pop(key, None)


def pending_steer(session_key: str | None = None) -> str | None:
    """Peek pending steer without clearing."""
    key = _resolve_session_key(session_key)
    with _lock:
        return _pending_by_session.get(key)


def apply_steer_to_tool_results(messages: list[dict[str, Any]], num_tool_msgs: int) -> bool:
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


def format_steer_gateway_reply(*, accepted: bool, active: bool) -> str:
    if not active:
        return (
            "当前没有进行中的 Agent 轮次，无法插入指引。"
            "请在任务执行过程中发送，或等待本轮结束后再开新对话。"
        )
    if accepted:
        return "已加入指引，将在下一批工具结果后注入（不打断当前工具执行）。"
    return "指引内容为空，未写入。"

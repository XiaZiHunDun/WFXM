"""Per-session cold-start gate — queue inbound until first warmup completes."""

from __future__ import annotations

import logging
import threading
from typing import Callable

from butler.env_parse import env_truthy

logger = logging.getLogger(__name__)

_LOCK = threading.RLock()
_WARMED: set[str] = set()
_WARMING: dict[str, threading.Lock] = {}


def session_initializing_enabled() -> bool:
    return env_truthy("BUTLER_GATEWAY_SESSION_INITIALIZING", default=True)


def format_initializing_ack(*, pending: int = 0) -> str:
    if pending > 0:
        return f"会话初始化中，消息已排队（{pending} 条），就绪后自动处理。"
    return "会话初始化中，消息已排队，就绪后自动处理。"


def _warming_lock(session_key: str) -> threading.Lock:
    key = str(session_key or "default")
    with _LOCK:
        lock = _WARMING.get(key)
        if lock is None:
            lock = threading.Lock()
            _WARMING[key] = lock
        return lock


def is_session_warmed(session_key: str) -> bool:
    key = str(session_key or "default")
    with _LOCK:
        return key in _WARMED


def mark_session_warmed(session_key: str) -> None:
    key = str(session_key or "default")
    with _LOCK:
        _WARMED.add(key)


def warmup_session(session_key: str, warmup_fn: Callable[[], None] | None = None) -> None:
    """Run one-time per-session warmup (skills index, etc.)."""
    if warmup_fn is not None:
        warmup_fn()
    mark_session_warmed(session_key)


def try_enter_session(
    session_key: str,
    warmup_fn: Callable[[], None] | None = None,
) -> str:
    """Return ``ready`` to proceed, or ``queued`` if another thread is warming."""
    if not session_initializing_enabled():
        return "ready"
    key = str(session_key or "default")
    lock = _warming_lock(key)
    if not lock.acquire(blocking=False):
        return "queued"
    try:
        if is_session_warmed(key):
            return "ready"
        logger.info("Gateway session warmup start session=%s", key)
        warmup_session(key, warmup_fn)
        logger.info("Gateway session warmup done session=%s", key)
        return "ready"
    finally:
        lock.release()


__all__ = [
    "format_initializing_ack",
    "is_session_warmed",
    "session_initializing_enabled",
    "try_enter_session",
    "warmup_session",
]

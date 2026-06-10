"""Session-scoped delegate concurrency limit (Sprint D)."""

from __future__ import annotations

import os
import threading
from contextlib import contextmanager
from typing import Iterator

from butler.env_parse import env_truthy, int_env

_LOCK = threading.Lock()
_SESSION_SLOTS: dict[str, int] = {}


def delegate_concurrency_enabled() -> bool:
    return env_truthy("BUTLER_DELEGATE_CONCURRENCY_LIMIT", default=True)


def max_concurrent_delegates() -> int:
    try:
        return max(1, int_env("BUTLER_DELEGATE_MAX_CONCURRENT", 2))
    except ValueError:
        return 2


def _slot_key(session_key: str) -> str:
    return str(session_key or "default").strip() or "default"


def try_acquire_delegate_slot(session_key: str) -> bool:
    if not delegate_concurrency_enabled():
        return True
    key = _slot_key(session_key)
    cap = max_concurrent_delegates()
    with _LOCK:
        used = _SESSION_SLOTS.get(key, 0)
        if used >= cap:
            return False
        _SESSION_SLOTS[key] = used + 1
    return True


def release_delegate_slot(session_key: str) -> None:
    if not delegate_concurrency_enabled():
        return
    key = _slot_key(session_key)
    with _LOCK:
        n = _SESSION_SLOTS.get(key, 1) - 1
        if n <= 0:
            _SESSION_SLOTS.pop(key, None)
        else:
            _SESSION_SLOTS[key] = n


@contextmanager
def acquire_delegate_slot(session_key: str) -> Iterator[None]:
    if not try_acquire_delegate_slot(session_key):
        cap = max_concurrent_delegates()
        raise RuntimeError(
            f"本会话并发委派已达上限 ({cap})，请等待进行中的任务完成。"
        )
    try:
        yield
    finally:
        release_delegate_slot(session_key)


def running_delegate_count(session_key: str = "") -> int:
    with _LOCK:
        return _SESSION_SLOTS.get(_slot_key(session_key), 0)


__all__ = [
    "acquire_delegate_slot",
    "delegate_concurrency_enabled",
    "max_concurrent_delegates",
    "release_delegate_slot",
    "running_delegate_count",
    "try_acquire_delegate_slot",
]

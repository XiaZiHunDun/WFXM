"""Per-thread interrupt signaling for Butler tools and agent loop."""

from __future__ import annotations

import threading
from typing import Set

_lock = threading.Lock()
_active_threads: Set[int] = set()


def set_interrupt(active: bool, thread_id: int | None = None) -> None:
    tid = thread_id if thread_id is not None else threading.get_ident()
    with _lock:
        if active:
            _active_threads.add(tid)
        else:
            _active_threads.discard(tid)


def clear_interrupt(thread_id: int | None = None) -> None:
    set_interrupt(False, thread_id)


def is_interrupted(thread_id: int | None = None) -> bool:
    tid = thread_id if thread_id is not None else threading.get_ident()
    with _lock:
        return tid in _active_threads

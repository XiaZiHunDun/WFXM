"""Post-commit side-effect queue (OpenCode storage/db after-commit subset)."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

logger = logging.getLogger(__name__)

Callback = Callable[[], None]
_LOCK = threading.RLock()
_QUEUE: list[Callback] = []


def enqueue_after_commit(fn: Callback) -> None:
    """Schedule ``fn`` to run after the current transactional work succeeds."""
    if not callable(fn):
        return
    with _LOCK:
        _QUEUE.append(fn)


def pending_after_commit_count() -> int:
    with _LOCK:
        return len(_QUEUE)


def flush_after_commit(*, clear_on_error: bool = True) -> int:
    """Run queued callbacks in order. Returns how many ran successfully."""
    with _LOCK:
        tasks = list(_QUEUE)
        if clear_on_error:
            _QUEUE.clear()
        else:
            _QUEUE[:] = []

    from butler.core.post_commit_ops import run_after_commit_callback_safe

    ran = 0
    failed = 0
    for fn in tasks:
        if run_after_commit_callback_safe(fn):
            ran += 1
        else:
            failed += 1
            logger.warning("after_commit callback failed")
    if failed and not clear_on_error:
        with _LOCK:
            _QUEUE.extend(tasks[ran + failed :])
    return ran


def clear_after_commit_queue() -> None:
    with _LOCK:
        _QUEUE.clear()

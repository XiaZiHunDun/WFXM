"""Best-effort helpers for optional sub-paths (P0-A exception governance)."""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from collections.abc import Callable
from typing import TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

_RECENT_LOCK = threading.Lock()
_RECENT: deque[tuple[float, str, str]] = deque(maxlen=32)


def record_best_effort_skip(label: str, exc: BaseException) -> None:
    """Keep the last N skipped paths for /诊断."""
    with _RECENT_LOCK:
        _RECENT.append((time.time(), str(label or "?")[:48], str(exc)[:160]))


def recent_best_effort_skips(limit: int = 5) -> list[tuple[float, str, str]]:
    with _RECENT_LOCK:
        rows = list(_RECENT)
    return rows[-max(1, limit) :]


def safe_best_effort(
    fn: Callable[[], T],
    *,
    label: str,
    default: T | None = None,
) -> T | None:
    """Run ``fn``; on failure log at debug, count metric, and record for /诊断."""
    try:
        return fn()
    except Exception as exc:
        logger.debug("%s skipped: %s", label, exc)
        record_best_effort_skip(label, exc)
        try:
            from butler.ops.runtime_metrics import inc

            inc("best_effort_skip", labels={"path": str(label or "?")[:48]})
        except Exception:
            pass
        return default


__all__ = ["recent_best_effort_skips", "record_best_effort_skip", "safe_best_effort"]

"""Session-scoped metrics for gateway completion pushes (/诊断)."""

from __future__ import annotations

import threading
from typing import Any

_LOCK = threading.Lock()
_BY_SESSION: dict[str, dict[str, int]] = {}


def _bucket(session_key: str) -> dict[str, int]:
    key = str(session_key or "").strip() or "_global"
    with _LOCK:
        return _BY_SESSION.setdefault(
            key,
            {"sent": 0, "failed": 0, "enqueued": 0},
        )


def record_completion_push_sent(*, session_key: str = "") -> None:
    _bucket(session_key)["sent"] += 1


def record_completion_push_failed(*, session_key: str = "") -> None:
    _bucket(session_key)["failed"] += 1


def record_completion_push_enqueued(*, session_key: str = "") -> None:
    _bucket(session_key)["enqueued"] += 1


def reset_completion_telemetry(session_key: str | None = None) -> None:
    with _LOCK:
        if session_key is None:
            _BY_SESSION.clear()
            return
        key = str(session_key or "").strip() or "_global"
        _BY_SESSION.pop(key, None)


def completion_push_stats(session_key: str = "") -> dict[str, int]:
    key = str(session_key or "").strip() or "_global"
    with _LOCK:
        return dict(_BY_SESSION.get(key, {"sent": 0, "failed": 0, "enqueued": 0}))


def push_queue_pending_count(*, chat_id: str = "") -> int:
    """Count queued rows (best-effort; optional chat_id filter)."""
    try:
        from butler.runtime.push_queue import count_pending_pushes

        return count_pending_pushes(chat_id=chat_id or None)
    except Exception:
        return 0

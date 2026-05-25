"""Per-session inbound message priority queue (now > next > later)."""

from __future__ import annotations

import logging
import re
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Any

from butler.env_parse import env_truthy

logger = logging.getLogger(__name__)

_PRIORITY_ORDER = {"now": 0, "next": 1, "later": 2}


@dataclass(frozen=True)
class QueuedInbound:
    text: str
    priority: str
    platform: str = "unknown"
    external_id: str = ""
    enqueued_at: float = 0.0


_LOCK = threading.RLock()
_QUEUES: dict[str, deque[QueuedInbound]] = {}
_DEDUP_WINDOW_SEC = 2.0
_LAST_ENQUEUE: dict[str, tuple[str, float]] = {}


def message_queue_enabled() -> bool:
    return env_truthy("BUTLER_GATEWAY_MESSAGE_QUEUE", default=True)


def classify_inbound_priority(text: str) -> str:
    """Classify gateway inbound: ``now`` | ``next`` | ``later``."""
    stripped = (text or "").strip()
    lower = stripped.lower()
    if lower.startswith(("/urgent", "/紧急", "/now")):
        return "now"
    if lower.startswith(("/later", "/稍后")):
        return "later"
    return "next"


def _should_dedupe(session_key: str, text: str) -> bool:
    key = str(session_key or "default")
    now = time.monotonic()
    prev = _LAST_ENQUEUE.get(key)
    if prev and prev[0] == text.strip() and (now - prev[1]) < _DEDUP_WINDOW_SEC:
        return True
    _LAST_ENQUEUE[key] = (text.strip(), now)
    return False


def enqueue_inbound(
    session_key: str,
    text: str,
    *,
    platform: str = "unknown",
    external_id: str = "",
    priority: str | None = None,
) -> bool:
    """Queue a message while the session turn is active. Returns False if duplicate."""
    if not message_queue_enabled():
        return False
    body = (text or "").strip()
    if not body:
        return False
    key = str(session_key or "default")
    if _should_dedupe(key, body):
        logger.debug("Inbound queue dedupe session=%s", key)
        return False
    pri = priority or classify_inbound_priority(body)
    if pri not in _PRIORITY_ORDER:
        pri = "next"
    item = QueuedInbound(
        text=body,
        priority=pri,
        platform=platform,
        external_id=str(external_id or ""),
        enqueued_at=time.monotonic(),
    )
    with _LOCK:
        bucket = _QUEUES.setdefault(key, deque())
        bucket.append(item)
        bucket = deque(sorted(bucket, key=lambda x: _PRIORITY_ORDER.get(x.priority, 9)))
        _QUEUES[key] = bucket
    logger.info("Queued inbound session=%s priority=%s len=%d", key, pri, len(_QUEUES[key]))
    _refresh_queue_gauges(key)
    try:
        from butler.core.session_transcript import record_queue_operation

        record_queue_operation(key, pri, body)
    except Exception:
        pass
    return True


def _refresh_queue_gauges(session_key: str) -> None:
    try:
        from butler.ops.runtime_metrics import set_gauge

        key = str(session_key or "default")
        depth = pending_count(key)
        set_gauge("inbound_queue_depth", float(depth), session_key=key)
        set_gauge("inbound_queue_depth_total", float(pending_total()))
    except Exception:
        pass


def pending_total() -> int:
    with _LOCK:
        return sum(len(bucket) for bucket in _QUEUES.values())


def pop_next(session_key: str) -> QueuedInbound | None:
    key = str(session_key or "default")
    with _LOCK:
        bucket = _QUEUES.get(key)
        if not bucket:
            return None
        item = bucket.popleft()
        if not bucket:
            _QUEUES.pop(key, None)
    _refresh_queue_gauges(key)
    return item


def pending_count(session_key: str = "") -> int:
    key = str(session_key or "default")
    with _LOCK:
        return len(_QUEUES.get(key, ()))


def reset_queue(session_key: str | None = None) -> None:
    with _LOCK:
        if session_key is None:
            _QUEUES.clear()
            _LAST_ENQUEUE.clear()
        else:
            key = str(session_key or "default")
            _QUEUES.pop(key, None)
            _LAST_ENQUEUE.pop(key, None)
    try:
        from butler.ops.runtime_metrics import set_gauge

        if session_key is None:
            set_gauge("inbound_queue_depth_total", 0.0)
        else:
            _refresh_queue_gauges(session_key)
    except Exception:
        pass


def format_queued_ack(*, pending: int = 1) -> str:
    if pending > 1:
        return f"已收到（队列中还有 {pending} 条），当前轮次结束后继续处理。"
    return "已收到，当前轮次结束后继续处理。"

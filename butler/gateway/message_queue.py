"""Per-session inbound message priority queue (now > next > later).

Supports optional JSONL-backed persistence so queued messages survive
gateway restarts.  Controlled by ``BUTLER_GATEWAY_QUEUE_PERSIST`` (default off).
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field as dc_field
from pathlib import Path

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
    persist_id: str = dc_field(default_factory=lambda: uuid.uuid4().hex[:12])


_LOCK = threading.RLock()
_QUEUES: dict[str, deque[QueuedInbound]] = {}
_DEDUP_WINDOW_SEC = 2.0
_LAST_ENQUEUE: dict[str, tuple[str, float]] = {}
_DROP_SUMMARIES: dict[str, deque[str]] = {}
_SUMMARY_MAX = 8


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


def _record_queue_drop(session_key: str, *, reason: str, count: int = 1) -> None:
    try:
        from butler.ops.runtime_metrics import inc

        inc(
            "inbound_queue_drop",
            labels={"reason": reason[:24]},
            session_key=session_key,
            value=count,
        )
        from butler.core.session_transcript import record_queue_drop

        record_queue_drop(session_key, reason, count)
    except Exception as exc:
        logger.debug("record queue drop skipped: %s", exc)
def _summarize_dropped(text: str) -> str:
    preview = re.sub(r"\s+", " ", (text or "").strip())[:120]
    return preview or "（空消息）"


def _apply_cap_before_append(session_key: str, bucket: deque[QueuedInbound], incoming: str) -> bool:
    """Make room for one more item. Returns False if incoming rejected (drop=new)."""
    from butler.gateway.queue_settings import session_drop_policy, session_queue_cap

    key = str(session_key or "default")
    cap = session_queue_cap(key)
    drop = session_drop_policy(key)
    while len(bucket) >= cap:
        if drop == "new":
            _record_queue_drop(key, reason="new")
            return False
        if not bucket:
            break
        if drop == "old":
            bucket.popleft()
            _record_queue_drop(key, reason="old")
            continue
        # summarize
        removed = bucket.popleft()
        summary = _summarize_dropped(removed.text)
        summaries = _DROP_SUMMARIES.setdefault(key, deque(maxlen=_SUMMARY_MAX))
        summaries.append(summary)
        _record_queue_drop(key, reason="summarize")
    return True


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
        if not _apply_cap_before_append(key, bucket, body):
            return False
        bucket.append(item)
        bucket = deque(sorted(bucket, key=lambda x: _PRIORITY_ORDER.get(x.priority, 9)))
        _QUEUES[key] = bucket
    _persist_enqueue(key, item)
    logger.info("Queued inbound session=%s priority=%s len=%d", key, pri, len(_QUEUES[key]))
    _refresh_queue_gauges(key)
    try:
        from butler.core.session_transcript import record_queue_operation

        record_queue_operation(key, pri, body)
    except Exception as exc:
        logger.debug("enqueue inbound skipped: %s", exc)
    return True


def _refresh_queue_gauges(session_key: str) -> None:
    try:
        from butler.ops.runtime_metrics import set_gauge

        key = str(session_key or "default")
        depth = pending_count(key)
        set_gauge("inbound_queue_depth", float(depth), session_key=key)
        set_gauge("inbound_queue_depth_total", float(pending_total()))
    except Exception as exc:
        logger.debug("refresh queue gauges skipped: %s", exc)
def pending_total() -> int:
    with _LOCK:
        return sum(len(bucket) for bucket in _QUEUES.values())


def pop_urgent_inbound(session_key: str) -> QueuedInbound | None:
    """Pop one ``now`` priority item if at queue head (mid-turn compaction bridge)."""
    key = str(session_key or "default")
    with _LOCK:
        bucket = _QUEUES.get(key)
        if not bucket:
            return None
        first = bucket[0]
        if first.priority != "now":
            return None
        item = bucket.popleft()
        if not bucket:
            _QUEUES.pop(key, None)
    _persist_remove(key, item.persist_id)
    _refresh_queue_gauges(key)
    return item


def pop_next(session_key: str) -> QueuedInbound | None:
    key = str(session_key or "default")
    with _LOCK:
        bucket = _QUEUES.get(key)
        if not bucket:
            return None
        item = bucket.popleft()
        if not bucket:
            _QUEUES.pop(key, None)
    _persist_remove(key, item.persist_id)
    _refresh_queue_gauges(key)
    return item


def pop_all_merged(session_key: str) -> QueuedInbound | None:
    """Drain entire queue into one synthetic followup item (collect mode)."""
    key = str(session_key or "default")
    with _LOCK:
        bucket = _QUEUES.get(key)
        items = list(bucket) if bucket else []
        if bucket:
            bucket.clear()
            _QUEUES.pop(key, None)
        summaries = list(_DROP_SUMMARIES.pop(key, ()))
    _persist_clear(key)
    _refresh_queue_gauges(key)
    if not items and not summaries:
        return None
    parts: list[str] = []
    if summaries:
        joined = "；".join(summaries)
        parts.append(f"[此前队列溢出摘要，共 {len(summaries)} 条] {joined}")
    for item in sorted(items, key=lambda x: _PRIORITY_ORDER.get(x.priority, 9)):
        parts.append(item.text)
    text = "\n\n".join(parts)
    last = items[-1] if items else None
    return QueuedInbound(
        text=text,
        priority="next",
        platform=last.platform if last else "unknown",
        external_id=last.external_id if last else "",
        enqueued_at=time.monotonic(),
    )


def pending_count(session_key: str = "") -> int:
    key = str(session_key or "default")
    with _LOCK:
        return len(_QUEUES.get(key, ()))


def reset_queue(session_key: str | None = None) -> None:
    with _LOCK:
        if session_key is None:
            _QUEUES.clear()
            _LAST_ENQUEUE.clear()
            _DROP_SUMMARIES.clear()
        else:
            key = str(session_key or "default")
            _QUEUES.pop(key, None)
            _LAST_ENQUEUE.pop(key, None)
            _DROP_SUMMARIES.pop(key, None)
    _persist_clear(session_key)
    try:
        from butler.ops.runtime_metrics import set_gauge

        if session_key is None:
            set_gauge("inbound_queue_depth_total", 0.0)
        else:
            _refresh_queue_gauges(session_key)
    except Exception as exc:
        logger.debug("reset queue skipped: %s", exc)
# ---------------------------------------------------------------------------
# Persistence layer — JSONL-backed durable queue
# ---------------------------------------------------------------------------


def _queue_persist_enabled() -> bool:
    return env_truthy("BUTLER_GATEWAY_QUEUE_PERSIST", default=False)


def _queue_persist_dir() -> Path:
    from butler.config import get_butler_home

    return get_butler_home() / "gateway" / "queue"


def _persist_enqueue(session_key: str, item: QueuedInbound) -> None:
    """Append a queue entry to the session's JSONL file."""
    if not _queue_persist_enabled():
        return
    try:
        root = _queue_persist_dir()
        root.mkdir(parents=True, exist_ok=True)
        safe_key = re.sub(r"[^\w\-]", "_", session_key)[:120]
        path = root / f"{safe_key}.jsonl"
        row = {
            "id": item.persist_id,
            "text": item.text,
            "priority": item.priority,
            "platform": item.platform,
            "external_id": item.external_id,
            "enqueued_at": item.enqueued_at,
        }
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.debug("Queue persist write failed: %s", exc)


def _persist_remove(session_key: str, persist_id: str) -> None:
    """Remove a single persisted entry by its id (rewrite minus the line)."""
    if not _queue_persist_enabled() or not persist_id:
        return
    try:
        root = _queue_persist_dir()
        safe_key = re.sub(r"[^\w\-]", "_", session_key)[:120]
        path = root / f"{safe_key}.jsonl"
        if not path.is_file():
            return
        lines = path.read_text(encoding="utf-8").splitlines()
        kept = [ln for ln in lines if persist_id not in ln]
        if len(kept) == len(lines):
            return
        if kept:
            path.write_text("\n".join(kept) + "\n", encoding="utf-8")
        else:
            path.unlink(missing_ok=True)
    except Exception as exc:
        logger.debug("Queue persist remove failed: %s", exc)


def _persist_clear(session_key: str | None = None) -> None:
    """Clear persisted queue file(s)."""
    if not _queue_persist_enabled():
        return
    try:
        root = _queue_persist_dir()
        if not root.is_dir():
            return
        if session_key is None:
            for f in root.glob("*.jsonl"):
                f.unlink(missing_ok=True)
        else:
            safe_key = re.sub(r"[^\w\-]", "_", session_key)[:120]
            (root / f"{safe_key}.jsonl").unlink(missing_ok=True)
    except Exception as exc:
        logger.debug("Queue persist clear failed: %s", exc)


def restore_persisted_queue() -> int:
    """Reload queued messages from disk into in-memory queues on startup.

    Returns the total number of restored items.
    """
    if not _queue_persist_enabled():
        return 0
    root = _queue_persist_dir()
    if not root.is_dir():
        return 0
    total = 0
    for path in sorted(root.glob("*.jsonl")):
        session_key = path.stem
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        items: list[QueuedInbound] = []
        for ln in lines:
            ln = ln.strip()
            if not ln:
                continue
            try:
                row = json.loads(ln)
                items.append(QueuedInbound(
                    text=row["text"],
                    priority=row.get("priority", "next"),
                    platform=row.get("platform", "unknown"),
                    external_id=row.get("external_id", ""),
                    enqueued_at=row.get("enqueued_at", 0.0),
                    persist_id=row.get("id", uuid.uuid4().hex[:12]),
                ))
            except (json.JSONDecodeError, KeyError):
                continue
        if items:
            with _LOCK:
                bucket = _QUEUES.setdefault(session_key, deque())
                bucket.extend(items)
                _QUEUES[session_key] = deque(
                    sorted(bucket, key=lambda x: _PRIORITY_ORDER.get(x.priority, 9))
                )
            total += len(items)
            logger.info("Restored %d queued messages for session %s", len(items), session_key)
    if total:
        logger.info("Queue persistence restored %d total items", total)
    return total


def format_queued_ack(*, pending: int = 1, session_key: str = "") -> str:
    base = (
        f"已收到（队列中还有 {pending} 条），当前轮次结束后继续处理。"
        if pending > 1
        else "已收到，当前轮次结束后继续处理。"
    )
    if session_key:
        try:
            from butler.gateway.queue_settings import get_queue_mode

            mode = get_queue_mode(session_key)
            if mode != "followup":
                base += f"（队列模式：{mode}）"
        except Exception as exc:
            logger.debug("format queued ack skipped: %s", exc)
    return base

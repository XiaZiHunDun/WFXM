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
# Sprint 11 PERF-11-1: 3 桶 per session（now/next/later），enqueue O(1)。
# 原实现是单 deque + 每次 enqueue O(N log N) sort，高频 inbound 线性退化。
# 桶内保持 FIFO；跨桶顺序：now > next > later（与原 sort 一致）。
_QUEUES: dict[str, dict[str, deque[QueuedInbound]]] = {}
_QUEUES_MAX_SESSIONS = 256
_DEDUP_WINDOW_SEC = 2.0
_LAST_ENQUEUE: dict[str, tuple[str, float]] = {}
_DROP_SUMMARIES: dict[str, deque[str]] = {}
_SUMMARY_MAX = 8
_PRIORITIES: tuple[str, ...] = ("now", "next", "later")


def _ensure_bucket(key: str) -> dict[str, deque[QueuedInbound]]:
    """Return the 3-bucket dict for session, creating if absent."""
    bucket = _QUEUES.get(key)
    if bucket is None:
        bucket = {p: deque() for p in _PRIORITIES}
        _QUEUES[key] = bucket
    return bucket


def _bucket_total(bucket: dict[str, deque[QueuedInbound]]) -> int:
    return sum(len(bucket[p]) for p in _PRIORITIES)


def _bucket_pop_oldest(bucket: dict[str, deque[QueuedInbound]]) -> QueuedInbound | None:
    """Pop from the lowest-priority non-empty bucket (later > next > now)."""
    for p in reversed(_PRIORITIES):
        if bucket[p]:
            return bucket[p].popleft()
    return None


def message_queue_enabled() -> bool:
    return env_truthy("BUTLER_GATEWAY_MESSAGE_QUEUE", default=True)


def classify_inbound_priority(text: str) -> str:
    """Classify gateway inbound: ``now`` | ``next`` | ``later``.

    Sprint 16 TST-10-5 第八批: ``/urgent`` ``/紧急`` ``/now`` 和 ``/later`` ``/稍后`` 是
    **priority tag (priority prefix)**, 不是 slash dispatch 命令. 它们在 inbound 入队前
    被识别为 priority hint (e.g. ``/urgent foo`` → "now" priority 整段入队), 不走
    ``_is_sessionless_command`` 或 ``dispatch()`` 路径. CommandDef 已从 registry 移除
    (Sprint 16 第八批). 用户文档保留这些名字作为 priority hint 提示, 但不视为可执行命令.
    """
    stripped = (text or "").strip()
    lower = stripped.lower()
    if lower.startswith(("/urgent", "/紧急", "/now")):
        return "now"
    if lower.startswith(("/later", "/稍后")):
        return "later"
    return "next"


_LAST_ENQUEUE_MAX = 512


def _should_dedupe(session_key: str, text: str) -> bool:
    key = str(session_key or "default")
    now = time.monotonic()
    prev = _LAST_ENQUEUE.get(key)
    if prev and prev[0] == text.strip() and (now - prev[1]) < _DEDUP_WINDOW_SEC:
        return True
    if len(_LAST_ENQUEUE) >= _LAST_ENQUEUE_MAX:
        stale = [
            k for k, (_, ts) in _LAST_ENQUEUE.items()
            if (now - ts) > _DEDUP_WINDOW_SEC * 10
        ]
        for k in stale:
            _LAST_ENQUEUE.pop(k, None)
        if len(_LAST_ENQUEUE) >= _LAST_ENQUEUE_MAX:
            oldest = next(iter(_LAST_ENQUEUE))
            _LAST_ENQUEUE.pop(oldest, None)
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


def _apply_cap_before_append(session_key: str, bucket: dict[str, deque[QueuedInbound]], incoming: str) -> bool:
    """Make room for one more item. Returns False if incoming rejected (drop=new).

    Sprint 11 PERF-11-1: 3 桶结构下，cap 检查汇总 3 桶总长；evict
    从最低优先级（later → next → now）开始 popleft，保留高优先级。
    """
    from butler.gateway.queue_settings import session_drop_policy, session_queue_cap

    key = str(session_key or "default")
    cap = session_queue_cap(key)
    drop = session_drop_policy(key)
    while _bucket_total(bucket) >= cap:
        if drop == "new":
            _record_queue_drop(key, reason="new")
            return False
        if _bucket_total(bucket) == 0:
            break
        if drop == "old":
            removed = _bucket_pop_oldest(bucket)
            if removed is None:
                break
            _record_queue_drop(key, reason="old")
            continue
        # summarize
        removed = _bucket_pop_oldest(bucket)
        if removed is None:
            break
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
        if _should_dedupe(key, body):
            logger.debug("Inbound queue dedupe session=%s", key)
            return False
        if len(_QUEUES) >= _QUEUES_MAX_SESSIONS and key not in _QUEUES:
            empty_keys = [k for k, b in _QUEUES.items() if _bucket_total(b) == 0]
            for ek in empty_keys:
                _QUEUES.pop(ek, None)
                _DROP_SUMMARIES.pop(ek, None)
        bucket = _ensure_bucket(key)
        if not _apply_cap_before_append(key, bucket, body):
            return False
        # Sprint 11 PERF-11-1: O(1) append to priority bucket, no sort
        bucket[pri].append(item)
    _persist_enqueue(key, item)
    logger.info("Queued inbound session=%s priority=%s len=%d", key, pri, _bucket_total(bucket))
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
        return sum(_bucket_total(b) for b in _QUEUES.values())


def pop_urgent_inbound(session_key: str) -> QueuedInbound | None:
    """Pop one ``now`` priority item if at queue head (mid-turn compaction bridge).

    Sprint 11 PERF-11-1: 3 桶结构下，直接从 now 桶 popleft，O(1)。
    """
    key = str(session_key or "default")
    item: QueuedInbound | None = None
    with _LOCK:
        bucket = _QUEUES.get(key)
        if bucket and bucket["now"]:
            item = bucket["now"].popleft()
            if _bucket_total(bucket) == 0:
                _QUEUES.pop(key, None)
    if item is None:
        return None
    _persist_remove(key, item.persist_id)
    _refresh_queue_gauges(key)
    return item


def pop_next(session_key: str) -> QueuedInbound | None:
    """Pop next item in priority order: now > next > later, FIFO within each."""
    key = str(session_key or "default")
    item: QueuedInbound | None = None
    with _LOCK:
        bucket = _QUEUES.get(key)
        if bucket:
            for p in _PRIORITIES:
                if bucket[p]:
                    item = bucket[p].popleft()
                    if _bucket_total(bucket) == 0:
                        _QUEUES.pop(key, None)
                    break
    if item is None:
        return None
    _persist_remove(key, item.persist_id)
    _refresh_queue_gauges(key)
    return item


def pop_all_merged(session_key: str) -> QueuedInbound | None:
    """Drain entire queue into one synthetic followup item (collect mode).

    Sprint 11 PERF-11-1: 3 桶结构下，合并时按 now → next → later 桶顺序。
    """
    key = str(session_key or "default")
    with _LOCK:
        bucket = _QUEUES.get(key)
        items: list[QueuedInbound] = []
        if bucket:
            for p in _PRIORITIES:
                items.extend(bucket[p])
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
    for item in items:
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
        bucket = _QUEUES.get(key)
        return _bucket_total(bucket) if bucket else 0


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
        logger.warning("Queue persist write failed: %s", exc)


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
        marker = f'"id": "{persist_id}"'
        kept = [ln for ln in lines if marker not in ln]
        if len(kept) == len(lines):
            return
        if kept:
            from butler.io.atomic_write import atomic_write_text

            atomic_write_text(path, "\n".join(kept) + "\n")
        else:
            path.unlink(missing_ok=True)
    except Exception as exc:
        logger.warning("Queue persist remove failed: %s", exc)


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
        logger.warning("Queue persist clear failed: %s", exc)


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
                    persist_id=row["id"] if "id" in row else uuid.uuid4().hex[:12],
                ))
            except (json.JSONDecodeError, KeyError):
                continue
        if items:
            from butler.gateway.queue_settings import session_queue_cap

            cap = session_queue_cap(session_key)
            with _LOCK:
                bucket = _ensure_bucket(session_key)
                # Sprint 11 PERF-11-1: 直接 append 到对应 priority 桶，O(N)
                added = 0
                for it in items:
                    if added >= cap:
                        break
                    p = it.priority if it.priority in _PRIORITY_ORDER else "next"
                    bucket[p].append(it)
                    added += 1
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

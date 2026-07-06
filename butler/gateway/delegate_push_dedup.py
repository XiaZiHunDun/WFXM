"""PROD-P5-01: suppress duplicate or stale delegate completion WeChat pushes."""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from pathlib import Path
from types import TracebackType
from typing import Any, cast

logger = logging.getLogger(__name__)

_TASK_ID_RE = re.compile(r"\btask_[a-f0-9]{8,}\b", re.I)

_LOCK = threading.Lock()
_PUSHED: dict[str, float] = {}
_ACTIVE_INBOUND: dict[str, int] = {}
_DEFERRED: dict[str, list[tuple[str, str]]] = {}


def delegate_push_dedup_enabled() -> bool:
    from butler.env_parse import env_truthy

    return bool(env_truthy("BUTLER_GATEWAY_DELEGATE_PUSH_DEDUP", default=True))


def defer_delegate_push_during_inbound_enabled() -> bool:
    from butler.env_parse import env_truthy

    return bool(env_truthy("BUTLER_GATEWAY_DEFER_DELEGATE_PUSH_DURING_INBOUND", default=True))


def delegate_push_max_age_seconds() -> float:
    from butler.env_parse import float_env

    return float(max(60.0, float_env("BUTLER_GATEWAY_DELEGATE_PUSH_MAX_AGE_SECONDS", 600.0)))


def extract_task_id_from_text(text: str) -> str:
    match = _TASK_ID_RE.search(str(text or ""))
    return match.group(0) if match else ""


def _dedup_key(chat_id: str, task_id: str) -> str:
    return f"{str(chat_id or '').strip()}::{str(task_id or '').strip()}"


def _task_completed_epoch(task_id: str) -> float | None:
    from butler.gateway.delegate_push_dedup_ops import task_completed_epoch_safe

    return cast("float | None", task_completed_epoch_safe(task_id))


def should_deliver_delegate_push(
    chat_id: str,
    task_id: str,
    *,
    body: str = "",
) -> tuple[bool, str]:
    """Return (ok, reason). reason empty when ok."""
    cid = str(chat_id or "").strip()
    tid = str(task_id or "").strip() or extract_task_id_from_text(body)
    if not delegate_push_dedup_enabled():
        return True, ""
    if not tid:
        return True, ""
    key = _dedup_key(cid, tid)
    with _LOCK:
        if key in _PUSHED:
            return False, "dedup:task_already_pushed"
    completed_at = _task_completed_epoch(tid)
    if completed_at is not None:
        age = time.time() - completed_at
        if age > delegate_push_max_age_seconds():
            return False, f"stale:age_{int(age)}s"
    return True, ""


def mark_delegate_push_delivered(chat_id: str, task_id: str, *, body: str = "") -> None:
    cid = str(chat_id or "").strip()
    tid = str(task_id or "").strip() or extract_task_id_from_text(body)
    if not tid:
        return
    key = _dedup_key(cid, tid)
    with _LOCK:
        _PUSHED[key] = time.time()
        if len(_PUSHED) > 500:
            cutoff = time.time() - 86400 * 2
            for k, ts in list(_PUSHED.items()):
                if ts < cutoff:
                    _PUSHED.pop(k, None)


def is_inbound_active(chat_id: str) -> bool:
    cid = str(chat_id or "").strip()
    if not cid:
        return False
    with _LOCK:
        return _ACTIVE_INBOUND.get(cid, 0) > 0


def defer_delegate_push(chat_id: str, body: str, *, kind: str = "delegate") -> None:
    cid = str(chat_id or "").strip()
    if not cid or not (body or "").strip():
        return
    with _LOCK:
        _DEFERRED.setdefault(cid, []).append((str(body), str(kind or "delegate")))


def flush_deferred_delegate_pushes(chat_id: str) -> list[tuple[str, str]]:
    cid = str(chat_id or "").strip()
    if not cid:
        return []
    with _LOCK:
        items = _DEFERRED.pop(cid, [])
    return items


class gateway_inbound_guard:
    """Mark chat inbound active; flush deferred delegate pushes on exit."""

    def __init__(self, chat_id: str) -> None:
        self.chat_id = str(chat_id or "").strip()

    def __enter__(self) -> gateway_inbound_guard:
        if not self.chat_id:
            return self
        with _LOCK:
            _ACTIVE_INBOUND[self.chat_id] = _ACTIVE_INBOUND.get(self.chat_id, 0) + 1
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if not self.chat_id:
            return
        flush = False
        with _LOCK:
            depth = _ACTIVE_INBOUND.get(self.chat_id, 0) - 1
            if depth <= 0:
                _ACTIVE_INBOUND.pop(self.chat_id, None)
                flush = True
            else:
                _ACTIVE_INBOUND[self.chat_id] = depth
        if flush and defer_delegate_push_during_inbound_enabled():
            self._flush_deferred()

    def _flush_deferred(self) -> None:
        items = flush_deferred_delegate_pushes(self.chat_id)
        if not items:
            return
        from butler.gateway.delegate_push_dedup_ops import flush_deferred_pushes_safe
        from butler.gateway.outbound_bridge import get_gateway_bridge_optional

        flush_deferred_pushes_safe(
            self.chat_id,
            items,
            bridge=get_gateway_bridge_optional(),
        )


def _schedule_deferred_push_standalone(chat_id: str, body: str, *, kind: str) -> None:
    """Best-effort when no live bridge (reuse runtime push path)."""
    from butler.gateway.delegate_push_dedup_ops import push_standalone_deferred_safe

    push_standalone_deferred_safe(chat_id, body)


def maybe_defer_delegate_push(chat_id: str, body: str, *, kind: str) -> bool:
    """If inbound active, queue push for after turn. Returns True if deferred."""
    if kind != "delegate" or not defer_delegate_push_during_inbound_enabled():
        return False
    if not is_inbound_active(chat_id):
        return False
    defer_delegate_push(chat_id, body, kind=kind)
    logger.info("delegate push deferred during inbound chat=%s", str(chat_id or "")[:12])
    return True


__all__ = [
    "defer_delegate_push_during_inbound_enabled",
    "delegate_push_dedup_enabled",
    "delegate_push_max_age_seconds",
    "extract_task_id_from_text",
    "flush_deferred_delegate_pushes",
    "gateway_inbound_guard",
    "is_inbound_active",
    "mark_delegate_push_delivered",
    "maybe_defer_delegate_push",
    "should_deliver_delegate_push",
]

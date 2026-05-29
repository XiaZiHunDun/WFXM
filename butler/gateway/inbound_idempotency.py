"""Platform message idempotency for gateway inbound (Firecrawl x-idempotency-key subset)."""

from __future__ import annotations

import logging
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Literal

from butler.env_parse import env_truthy

logger = logging.getLogger(__name__)

_LOCK = threading.RLock()
# session -> OrderedDict[external_id, (status, monotonic_ts)]
_SEEN: dict[str, OrderedDict[str, tuple[str, float]]] = {}
_MAX_IDS_PER_SESSION = 512
_MAX_SESSIONS = 256

Status = Literal["inflight", "done"]


def external_id_dedupe_enabled() -> bool:
    return env_truthy("BUTLER_GATEWAY_EXTERNAL_ID_DEDUPE", default=True)


@dataclass(frozen=True)
class InboundIdempotencyDecision:
    accept: bool
    reason: str = ""
    user_reply: str = ""

    @property
    def skip(self) -> bool:
        return not self.accept


def _normalize_external_id(external_id: str | None) -> str:
    return str(external_id or "").strip()


def _prune_session(bucket: OrderedDict[str, tuple[str, float]]) -> None:
    while len(bucket) > _MAX_IDS_PER_SESSION:
        bucket.popitem(last=False)


def check_and_reserve_inbound(
    session_key: str,
    external_id: str | None,
    *,
    text_preview: str = "",
) -> InboundIdempotencyDecision:
    """Reserve platform message id for this turn; reject duplicates."""
    if not external_id_dedupe_enabled():
        return InboundIdempotencyDecision(accept=True)
    eid = _normalize_external_id(external_id)
    if not eid:
        return InboundIdempotencyDecision(accept=True)

    sk = str(session_key or "default").strip() or "default"
    with _LOCK:
        if len(_SEEN) >= _MAX_SESSIONS and sk not in _SEEN:
            oldest = next(iter(_SEEN))
            _SEEN.pop(oldest, None)
        bucket = _SEEN.setdefault(sk, OrderedDict())
        prev = bucket.get(eid)
        if prev is not None:
            status, _ts = prev
            if status == "done":
                return InboundIdempotencyDecision(
                    accept=False,
                    reason="duplicate_done",
                    user_reply="（重复消息已忽略，此前已处理。）",
                )
            return InboundIdempotencyDecision(
                accept=False,
                reason="duplicate_inflight",
                user_reply="（相同消息正在处理中，请稍候。）",
            )
        bucket[eid] = ("inflight", time.monotonic())
        _prune_session(bucket)

    try:
        from butler.ops.runtime_metrics import inc

        inc("inbound_idempotency_reserve", session_key=sk)
    except Exception as exc:
        logger.debug("check and reserve inbound skipped: %s", exc)
    return InboundIdempotencyDecision(accept=True)


def complete_inbound(session_key: str, external_id: str | None) -> None:
    """Mark platform message as fully processed (success or failure)."""
    eid = _normalize_external_id(external_id)
    if not eid:
        return
    sk = str(session_key or "default").strip() or "default"
    with _LOCK:
        bucket = _SEEN.get(sk)
        if bucket is None:
            return
        bucket[eid] = ("done", time.monotonic())
        _prune_session(bucket)


def release_inflight(session_key: str, external_id: str | None) -> None:
    """Drop inflight reservation without marking done (e.g. suppressed bot loop)."""
    eid = _normalize_external_id(external_id)
    if not eid:
        return
    sk = str(session_key or "default").strip() or "default"
    with _LOCK:
        bucket = _SEEN.get(sk)
        if bucket is None:
            return
        status, _ = bucket.get(eid, ("", 0.0))
        if status == "inflight":
            bucket.pop(eid, None)


def reset_session(session_key: str | None = None) -> None:
    with _LOCK:
        if session_key is None:
            _SEEN.clear()
            return
        sk = str(session_key or "default").strip() or "default"
        _SEEN.pop(sk, None)


def record_duplicate_skip(
    session_key: str,
    *,
    reason: str,
    external_id: str = "",
    preview: str = "",
) -> None:
    try:
        from butler.ops.runtime_metrics import inc

        inc(
            "inbound_duplicate_skip",
            labels={"reason": str(reason or "?")[:24]},
            session_key=session_key,
        )
        from butler.core.session_transcript import record_generic_event

        record_generic_event(
            session_key,
            "inbound_duplicate_skip",
            {
                "reason": reason,
                "external_id": (external_id or "")[:64],
                "preview": (preview or "")[:120],
            },
        )
    except Exception as exc:
        logger.debug("record duplicate skip skipped: %s", exc)
__all__ = [
    "InboundIdempotencyDecision",
    "check_and_reserve_inbound",
    "complete_inbound",
    "external_id_dedupe_enabled",
    "record_duplicate_skip",
    "release_inflight",
    "reset_session",
]

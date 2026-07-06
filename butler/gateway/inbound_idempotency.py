"""Platform message idempotency for gateway inbound (Firecrawl x-idempotency-key subset)."""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Literal

from butler.env_parse import env_truthy

_LOCK = threading.RLock()
# session -> OrderedDict[external_id, (status, monotonic_ts)]
_SEEN: dict[str, OrderedDict[str, tuple[str, float]]] = {}
_MAX_IDS_PER_SESSION = 512
_MAX_SESSIONS = 256
# Sprint 11 REL-11-5: inflight 状态 TTL。worker 崩溃后 inflight 会卡
# 住 → 同 eid 后续消息一律 duplicate_inflight 拒绝。Lazy sweep
# 在 check_and_reserve / complete 时清理过期 inflight（避免后台线程
# + 复杂度）。默认 60s，可通过 BUTLER_GATEWAY_INFLIGHT_TTL_SEC 配置。
_INFLIGHT_TTL_SEC = 60.0

Status = Literal["inflight", "done"]


def external_id_dedupe_enabled() -> bool:
    return bool(env_truthy("BUTLER_GATEWAY_EXTERNAL_ID_DEDUPE", default=True))


def _resolve_inflight_ttl() -> float:
    """Read TTL from env (allow per-process override); fall back to default."""
    import os
    raw = os.getenv("BUTLER_GATEWAY_INFLIGHT_TTL_SEC", "").strip()
    if not raw:
        return _INFLIGHT_TTL_SEC
    try:
        v = float(raw)
        if v < 1.0:
            return _INFLIGHT_TTL_SEC
        return v
    except ValueError:
        return _INFLIGHT_TTL_SEC


def _sweep_expired_inflight(
    bucket: OrderedDict[str, tuple[str, float]],
    now: float,
    ttl: float,
) -> None:
    """Remove inflight entries older than ttl. Done entries are untouched.

    Sprint 11 REL-11-5: lazy sweep, 避免后台线程。
    """
    expired = [
        eid
        for eid, (status, ts) in bucket.items()
        if status == "inflight" and (now - ts) > ttl
    ]
    for eid in expired:
        bucket.pop(eid, None)


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
        # Sprint 11 REL-11-5: lazy sweep 过期 inflight（worker 崩溃恢复）
        _sweep_expired_inflight(bucket, time.monotonic(), _resolve_inflight_ttl())
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

    from butler.gateway.inbound_idempotency_ops import inc_inbound_idempotency_reserve_safe

    inc_inbound_idempotency_reserve_safe(sk)
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
        # Sprint 11 REL-11-5: 顺便 sweep 过期 inflight（清理 worker 崩溃残留）
        _sweep_expired_inflight(bucket, time.monotonic(), _resolve_inflight_ttl())
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
    from butler.gateway.inbound_idempotency_ops import record_duplicate_skip_telemetry_safe

    record_duplicate_skip_telemetry_safe(
        session_key,
        reason=reason,
        external_id=external_id,
        preview=preview,
    )
__all__ = [
    "InboundIdempotencyDecision",
    "check_and_reserve_inbound",
    "complete_inbound",
    "external_id_dedupe_enabled",
    "record_duplicate_skip",
    "release_inflight",
    "reset_session",
]

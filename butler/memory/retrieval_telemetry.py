"""Session-scoped retrieval telemetry for /诊断."""

from __future__ import annotations

import threading
import time
from typing import Any

_LOCK = threading.RLock()
_MAX = 128
# session_key -> scope -> telemetry item
_LAST_BY_SESSION: dict[str, dict[str, dict[str, Any]]] = {}


def _infer_scope(mode: str, payload: dict[str, Any]) -> str:
    explicit = str(payload.get("scope") or "").strip().lower()
    if explicit:
        return explicit
    m = str(mode or "").strip().lower()
    if m.startswith("project"):
        return "project"
    if m.startswith("profile"):
        return "profile"
    if m.startswith("coding"):
        return "coding"
    if m.startswith("transcript"):
        return "transcript"
    if m.startswith("observation"):
        return "observation"
    if m.startswith("hybrid"):
        return "hybrid"
    return "experience"


def _normalize_item(payload: dict[str, Any]) -> dict[str, Any]:
    item = {
        "mode": str(payload.get("mode") or "").strip(),
        "fallbacks": max(0, int(payload.get("fallbacks") or 0)),
        "candidates": max(0, int(payload.get("candidates") or 0)),
        "query": str(payload.get("query") or "")[:120],
        "ts": float(payload.get("ts") or time.time()),
        # Audit R2-2: True iff hybrid_search raised and the caller fell back
        # to FTS-only. Surfaces recall-quality collapse in /诊断 and any
        # prompt-side health reporting.
        "recall_degraded": bool(payload.get("recall_degraded")),
    }
    item["scope"] = _infer_scope(item["mode"], payload)
    subs = payload.get("sub_queries")
    if isinstance(subs, list) and subs:
        item["sub_queries"] = [str(s)[:80] for s in subs[:5]]
        item["sub_query_count"] = len(subs)
    return item


def _session_latest_ts(bucket: dict[str, dict[str, Any]]) -> float:
    if not bucket:
        return 0.0
    return max(float(v.get("ts") or 0.0) for v in bucket.values())


def record_last_retrieval(session_key: str, payload: dict[str, Any]) -> None:
    sk = str(session_key or "").strip()
    if not sk or not isinstance(payload, dict):
        return
    item = _normalize_item(payload)
    scope = item["scope"]
    with _LOCK:
        bucket = _LAST_BY_SESSION.setdefault(sk, {})
        bucket[scope] = item
        if len(_LAST_BY_SESSION) > _MAX:
            oldest = sorted(
                _LAST_BY_SESSION.items(),
                key=lambda kv: _session_latest_ts(kv[1]),
            )[: len(_LAST_BY_SESSION) - _MAX]
            for key, _ in oldest:
                _LAST_BY_SESSION.pop(key, None)
    if item.get("recall_degraded"):
        from butler.memory.retrieval_telemetry_ops import sync_recall_degradation_safe

        sync_recall_degradation_safe(recall_degraded=True)
    else:
        from butler.memory.retrieval_telemetry_ops import sync_recall_degradation_safe

        sync_recall_degradation_safe(recall_degraded=False)


def get_last_retrieval_by_scope(session_key: str) -> dict[str, dict[str, Any]]:
    sk = str(session_key or "").strip()
    if not sk:
        return {}
    with _LOCK:
        bucket = _LAST_BY_SESSION.get(sk) or {}
        return {scope: dict(item) for scope, item in bucket.items()}


def get_last_retrieval(session_key: str) -> dict[str, Any]:
    """Most recent retrieval across scopes (backward compatible)."""
    by_scope = get_last_retrieval_by_scope(session_key)
    if not by_scope:
        return {}
    return dict(max(by_scope.values(), key=lambda x: float(x.get("ts") or 0.0)))


def clear_last_retrieval(session_key: str) -> None:
    sk = str(session_key or "").strip()
    if not sk:
        return
    with _LOCK:
        _LAST_BY_SESSION.pop(sk, None)


__all__ = [
    "clear_last_retrieval",
    "get_last_retrieval",
    "get_last_retrieval_by_scope",
    "record_last_retrieval",
]

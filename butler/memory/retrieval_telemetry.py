"""Session-scoped retrieval telemetry for /诊断."""

from __future__ import annotations

import threading
import time
from typing import Any

_LOCK = threading.RLock()
_MAX = 128
_LAST_BY_SESSION: dict[str, dict[str, Any]] = {}


def record_last_retrieval(session_key: str, payload: dict[str, Any]) -> None:
    sk = str(session_key or "").strip()
    if not sk or not isinstance(payload, dict):
        return
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
    subs = payload.get("sub_queries")
    if isinstance(subs, list) and subs:
        item["sub_queries"] = [str(s)[:80] for s in subs[:5]]
        item["sub_query_count"] = len(subs)
    with _LOCK:
        _LAST_BY_SESSION[sk] = item
        if len(_LAST_BY_SESSION) > _MAX:
            oldest = sorted(_LAST_BY_SESSION.items(), key=lambda kv: kv[1].get("ts", 0.0))[
                : len(_LAST_BY_SESSION) - _MAX
            ]
            for key, _ in oldest:
                _LAST_BY_SESSION.pop(key, None)
    if item.get("recall_degraded"):
        try:
            from butler.ops.degradation_registry import register_degradation

            register_degradation("recall", "hybrid 异常，仅 FTS")
        except Exception:
            pass
    else:
        try:
            from butler.ops.degradation_registry import clear_degradation

            clear_degradation("recall")
        except Exception:
            pass


def get_last_retrieval(session_key: str) -> dict[str, Any]:
    sk = str(session_key or "").strip()
    if not sk:
        return {}
    with _LOCK:
        return dict(_LAST_BY_SESSION.get(sk) or {})


def clear_last_retrieval(session_key: str) -> None:
    sk = str(session_key or "").strip()
    if not sk:
        return
    with _LOCK:
        _LAST_BY_SESSION.pop(sk, None)


__all__ = ["clear_last_retrieval", "get_last_retrieval", "record_last_retrieval"]

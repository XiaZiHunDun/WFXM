"""Background warm-cache for per-turn memory prefetch (queue_prefetch)."""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Callable

logger = logging.getLogger(__name__)

_CACHE: dict[str, tuple[str, str, float]] = {}
_LOCK = threading.RLock()


def queue_prefetch_enabled() -> bool:
    return os.getenv("BUTLER_QUEUE_PREFETCH", "0").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def prefetch_cache_ttl_seconds() -> int:
    try:
        return max(5, int(os.getenv("BUTLER_PREFETCH_CACHE_TTL", "90")))
    except ValueError:
        return 90


def _cache_key(session_key: str, query: str) -> str:
    sk = str(session_key or "").strip() or "default"
    q = (query or "").strip()
    return f"{sk}:{hash(q) & 0xFFFFFFFF:08x}"


def get_cached_prefetch(session_key: str, query: str) -> str | None:
    key = _cache_key(session_key, query)
    ttl = prefetch_cache_ttl_seconds()
    now = time.monotonic()
    with _LOCK:
        entry = _CACHE.get(key)
        if not entry:
            return None
        cached_query, ctx, ts = entry
        if cached_query != (query or "").strip():
            return None
        if now - ts > ttl:
            _CACHE.pop(key, None)
            return None
        return ctx


def set_cached_prefetch(session_key: str, query: str, ctx: str) -> None:
    q = (query or "").strip()
    if not q or not (ctx or "").strip():
        return
    key = _cache_key(session_key, q)
    with _LOCK:
        _CACHE[key] = (q, ctx.strip(), time.monotonic())


def clear_prefetch_cache(session_key: str = "") -> None:
    sk = str(session_key or "").strip()
    with _LOCK:
        if not sk:
            _CACHE.clear()
            return
        drop = [k for k in _CACHE if k.startswith(f"{sk}:")]
        for k in drop:
            _CACHE.pop(k, None)


def schedule_prefetch_warm(
    fn: Callable[[], str],
    *,
    session_key: str,
    query: str,
) -> None:
    """Run prefetch in a daemon thread and store result for identical next query."""
    if not queue_prefetch_enabled():
        return
    q = (query or "").strip()
    if not q:
        return
    sk = str(session_key or "").strip() or "default"

    def _run() -> None:
        try:
            ctx = fn()
            if ctx.strip():
                set_cached_prefetch(sk, q, ctx)
        except Exception as exc:
            logger.debug("queue_prefetch warm failed: %s", exc)

    threading.Thread(target=_run, name=f"butler-prefetch-{sk[:24]}", daemon=True).start()

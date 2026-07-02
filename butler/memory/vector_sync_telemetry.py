"""Last vector upsert timestamps for /诊断 (P2-4)."""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone

_LOCK = threading.RLock()
_LAST_BY_SCOPE: dict[str, float] = {}


def record_vector_sync(scope: str, *, project: str = "") -> None:
    """Record a successful semantic index upsert for *scope*."""
    key = str(scope or "").strip().lower()
    if not key:
        return
    if project:
        key = f"{key}:{str(project).strip()}"
    with _LOCK:
        _LAST_BY_SCOPE[key] = time.time()


def get_vector_sync_times() -> dict[str, float]:
    with _LOCK:
        return dict(_LAST_BY_SCOPE)


def format_vector_sync_lines(limit: int = 5) -> list[str]:
    times = get_vector_sync_times()
    if not times:
        return []
    rows = sorted(times.items(), key=lambda kv: kv[1], reverse=True)[: max(1, limit)]
    lines = ["  最近向量写入:"]
    for key, ts in rows:
        try:
            stamp = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        except (OSError, OverflowError, ValueError):
            stamp = "?"
        lines.append(f"    {key}: {stamp}")
    return lines


__all__ = ["format_vector_sync_lines", "get_vector_sync_times", "record_vector_sync"]

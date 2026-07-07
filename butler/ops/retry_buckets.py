"""Retry / recovery reason counters for /诊断 (Firecrawl ScrapeRetryTracker subset)."""

from __future__ import annotations

from typing import cast

from butler.ops.runtime_metrics import inc, snapshot_global

def record_recovery_event(reason: str, *, session_key: str = "") -> None:
    """Increment a labeled recovery counter (process-wide + optional session)."""
    from butler.ops.retry_buckets_ops import inc_recovery_event_safe

    inc_recovery_event_safe(reason=reason, session_key=session_key)
def format_recovery_bucket_lines(*, session_key: str = "") -> list[str]:
    """Summarize recovery_event counters for health output."""
    from butler.ops.retry_buckets_ops import format_recovery_bucket_lines_safe

    lines = format_recovery_bucket_lines_safe(session_key=session_key)
    if not lines:
        return []
    return cast(list[str], lines)


__all__ = ["format_recovery_bucket_lines", "record_recovery_event"]

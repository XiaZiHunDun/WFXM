"""Cron schedule helpers (croniter)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, cast

from croniter import croniter  # type: ignore[import-untyped]


def job_is_due(schedule: str, *, now: Optional[datetime] = None) -> bool:
    """True if cron expression matches current minute (UTC)."""
    expr = (schedule or "").strip()
    if not expr:
        return False
    now = now or datetime.now(timezone.utc)
    try:
        it = croniter(expr, now)
        prev = it.get_prev(datetime)
        if prev.tzinfo is None:
            prev = prev.replace(tzinfo=timezone.utc)
        delta = (now - prev).total_seconds()
        return bool(delta < 90)
    except (ValueError, KeyError):
        return False


def format_schedule_hint(schedule: str) -> str:
    s = (schedule or "").strip()
    return s if s else "（手动）"


def next_run_iso(schedule: str, *, now: Optional[datetime] = None) -> str | None:
    """Next cron fire time (UTC ISO) or None."""
    expr = (schedule or "").strip()
    if not expr:
        return None
    now = now or datetime.now(timezone.utc)
    try:
        it = croniter(expr, now)
        nxt = it.get_next(datetime)
        if nxt.tzinfo is None:
            nxt = nxt.replace(tzinfo=timezone.utc)
        return cast(str, nxt.isoformat())
    except (ValueError, KeyError):
        return None

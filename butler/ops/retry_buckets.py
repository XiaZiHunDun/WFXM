"""Retry / recovery reason counters for /诊断 (Firecrawl ScrapeRetryTracker subset)."""

from __future__ import annotations

from butler.ops.runtime_metrics import inc, snapshot_global
import logging


logger = logging.getLogger(__name__)

def record_recovery_event(reason: str, *, session_key: str = "") -> None:
    """Increment a labeled recovery counter (process-wide + optional session)."""
    label = str(reason or "unknown").strip()[:32] or "unknown"
    try:
        inc("recovery_event", labels={"reason": label}, session_key=session_key)
    except Exception as exc:
        logger.debug("record recovery event skipped: %s", exc)
def format_recovery_bucket_lines(*, session_key: str = "") -> list[str]:
    """Summarize recovery_event counters for health output."""
    lines: list[str] = []
    try:
        if session_key:
            from butler.ops.runtime_metrics import snapshot_session

            snap = snapshot_session(session_key)
            counters = snap.get("counters") or {}
            prefixed = {
                k.replace("recovery_event{reason=", "").rstrip("}"): v
                for k, v in counters.items()
                if k.startswith("recovery_event{")
            }
            if prefixed:
                lines.append("恢复/重试分桶（本会话）:")
                for key in sorted(prefixed):
                    lines.append(f"  {key}: {prefixed[key]}")
        global_snap = snapshot_global()
        gc = global_snap.get("counters") or {}
        gprefixed = {
            k.replace("recovery_event{reason=", "").rstrip("}"): v
            for k, v in gc.items()
            if k.startswith("recovery_event{")
        }
        if gprefixed:
            lines.append("恢复/重试分桶（进程）:")
            for key in sorted(gprefixed):
                lines.append(f"  {key}: {gprefixed[key]}")
    except Exception as exc:
        logger.debug("format recovery bucket lines skipped: %s", exc)
    if not lines:
        return []
    return lines


__all__ = ["format_recovery_bucket_lines", "record_recovery_event"]

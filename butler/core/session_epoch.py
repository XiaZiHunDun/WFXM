"""Transcript epoch boundaries (/new clears tool-truth scope)."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

_SESSION_RESET = "session_reset"


def epoch_start_index(rows: list[dict[str, Any]]) -> int:
    """Return row index where the current epoch begins (after last session_reset)."""
    start = 0
    for i, row in enumerate(rows):
        if str(row.get("type") or "") == _SESSION_RESET:
            start = i + 1
    return start


def rows_in_current_epoch(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not rows:
        return []
    idx = epoch_start_index(rows)
    return rows[idx:]


def load_epoch_transcript_rows(
    session_key: str,
    *,
    max_lines: int | None = None,
) -> list[dict[str, Any]]:
    try:
        from butler.core.transcript_export import load_transcript_rows
    except Exception as exc:
        logger.debug("epoch transcript load skipped: %s", exc)
        return []
    rows = load_transcript_rows(session_key, max_lines=max_lines)
    return rows_in_current_epoch(rows)


def _parse_ts(ts: str) -> float | None:
    text = str(ts or "").strip()
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return dt.timestamp()
    except ValueError:
        return None


def last_assistant_ts_in_epoch(session_key: str) -> float | None:
    rows = load_epoch_transcript_rows(session_key, max_lines=80)
    for row in reversed(rows):
        if str(row.get("type") or "") != "assistant":
            continue
        ts = _parse_ts(str(row.get("ts") or ""))
        if ts is not None:
            return ts
    return None


__all__ = [
    "epoch_start_index",
    "last_assistant_ts_in_epoch",
    "load_epoch_transcript_rows",
    "rows_in_current_epoch",
]

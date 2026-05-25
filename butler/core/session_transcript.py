"""Append-only session transcript JSONL (Claude Code sessionStorage subset)."""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from butler.config import get_butler_home
from butler.env_parse import env_truthy

logger = logging.getLogger(__name__)

_TRANSCRIPT_SUBDIR = "sessions"
_DEFAULT_MAX_BYTES = 50 * 1024 * 1024
_LOCK = threading.RLock()


def transcript_enabled() -> bool:
    return env_truthy("BUTLER_SESSION_TRANSCRIPT", default=True)


def transcript_max_bytes() -> int:
    try:
        return max(1_000_000, int(os.getenv("BUTLER_SESSION_TRANSCRIPT_MAX_BYTES", "") or _DEFAULT_MAX_BYTES))
    except ValueError:
        return _DEFAULT_MAX_BYTES


def _safe_segment(value: str) -> str:
    import re

    raw = str(value or "").strip() or "_global"
    return re.sub(r"[^a-zA-Z0-9._+-]+", "_", raw)[:120] or "_global"


def transcript_path(session_key: str) -> Path:
    sk = _safe_segment(session_key)
    return get_butler_home() / _TRANSCRIPT_SUBDIR / sk / "transcript.jsonl"


def _append_line(path: Path, entry: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(entry, ensure_ascii=False) + "\n"
    with _LOCK:
        with path.open("a", encoding="utf-8") as fh:
            fh.write(line)
        if path.stat().st_size > transcript_max_bytes():
            _tombstone_tail(path)


def _tombstone_tail(path: Path) -> None:
    """Keep last ~40% of lines when file exceeds max size."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    if len(lines) < 20:
        return
    keep = max(10, len(lines) // 2)
    marker = {
        "type": "tombstone",
        "ts": datetime.now(timezone.utc).isoformat(),
        "dropped_lines": len(lines) - keep,
    }
    tail = lines[-keep:]
    try:
        with path.open("w", encoding="utf-8") as fh:
            fh.write(json.dumps(marker, ensure_ascii=False) + "\n")
            for ln in tail:
                fh.write(ln + "\n")
    except OSError as exc:
        logger.warning("Transcript tombstone failed: %s", exc)


def append_transcript_entry(
    session_key: str,
    entry_type: str,
    payload: dict[str, Any],
) -> None:
    if not transcript_enabled():
        return
    sk = str(session_key or "").strip()
    if not sk:
        return
    entry = {
        "type": entry_type,
        "ts": datetime.now(timezone.utc).isoformat(),
        **payload,
    }
    try:
        _append_line(transcript_path(sk), entry)
    except OSError as exc:
        logger.debug("Transcript append skipped: %s", exc)


def record_user_message(session_key: str, content: str) -> None:
    append_transcript_entry(
        session_key,
        "user",
        {"content_preview": (content or "")[:500]},
    )


def record_assistant_message(session_key: str, content: str, *, tool_calls: int = 0) -> None:
    append_transcript_entry(
        session_key,
        "assistant",
        {
            "content_preview": (content or "")[:500],
            "tool_calls": tool_calls,
        },
    )


def record_compact_boundary(session_key: str, summary_chars: int) -> None:
    append_transcript_entry(
        session_key,
        "compact_boundary",
        {"summary_chars": summary_chars},
    )


def record_compact_scheduled(
    session_key: str,
    *,
    source: str = "context",
    messages_before: int = 0,
    tokens_estimated: int = 0,
) -> None:
    append_transcript_entry(
        session_key,
        "compact_scheduled",
        {
            "source": str(source or "context")[:32],
            "messages_before": max(0, int(messages_before)),
            "tokens_estimated": max(0, int(tokens_estimated)),
        },
    )


def record_compact_done(
    session_key: str,
    *,
    source: str = "context",
    messages_after: int = 0,
    tokens_after: int = 0,
    summary_chars: int = 0,
) -> None:
    append_transcript_entry(
        session_key,
        "compact_done",
        {
            "source": str(source or "context")[:32],
            "messages_after": max(0, int(messages_after)),
            "tokens_after": max(0, int(tokens_after)),
            "summary_chars": max(0, int(summary_chars)),
        },
    )


def record_todo_updated(session_key: str, *, count: int = 0) -> None:
    append_transcript_entry(
        session_key,
        "todo_updated",
        {"count": max(0, int(count))},
    )


def record_tool_spill_pointer(session_key: str, tool_use_id: str, path: str) -> None:
    append_transcript_entry(
        session_key,
        "tool_spill_pointer",
        {"tool_use_id": tool_use_id, "path": path},
    )


def record_queue_operation(session_key: str, priority: str, preview: str) -> None:
    append_transcript_entry(
        session_key,
        "queue_op",
        {"priority": priority, "preview": preview[:200]},
    )


def record_queue_drop(session_key: str, reason: str, count: int = 1) -> None:
    append_transcript_entry(
        session_key,
        "queue_drop",
        {"reason": str(reason or "?")[:32], "count": max(1, int(count))},
    )


def load_transcript_tail(session_key: str, *, max_lines: int = 50) -> list[dict[str, Any]]:
    path = transcript_path(session_key)
    if not path.is_file():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out: list[dict[str, Any]] = []
    for ln in lines[-max_lines:]:
        try:
            row = json.loads(ln)
            if isinstance(row, dict):
                out.append(row)
        except json.JSONDecodeError:
            continue
    return out

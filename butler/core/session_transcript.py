"""Append-only session transcript JSONL (Claude Code sessionStorage subset)."""

from __future__ import annotations

import json
import logging
import os
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from butler.config import get_butler_home
from butler.env_parse import env_truthy

logger = logging.getLogger(__name__)

_TRANSCRIPT_SUBDIR = "sessions"
_DEFAULT_MAX_BYTES = 50 * 1024 * 1024
_LOCK = threading.RLock()

# PERF-13-3: 批量写 buffer
_BATCH_LOCK = threading.RLock()
_ACTIVE_BATCHES: set[str] = set()
_BATCH_BUFFERS: dict[str, list[dict[str, Any]]] = {}


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
        offset = path.stat().st_size if path.is_file() else 0
        with path.open("a", encoding="utf-8") as fh:
            fh.write(line)
        try:
            from butler.core.transcript_index import update_index_after_append

            update_index_after_append(path, line_byte_offset=offset, line_len=len(line.encode("utf-8")))
        except Exception as exc:
            logger.debug("append line skipped: %s", exc)
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
    parsed_rows: list[dict[str, Any]] = []
    for ln in lines:
        try:
            row = json.loads(ln)
            if isinstance(row, dict):
                parsed_rows.append(row)
        except json.JSONDecodeError:
            continue
    if parsed_rows:
        from butler.core.transcript_retention import select_transcript_rows_for_retention

        kept_rows = select_transcript_rows_for_retention(parsed_rows, keep_count=keep)
        tail = [json.dumps(row, ensure_ascii=False) for row in kept_rows]
    else:
        tail = lines[-keep:]
    try:
        from butler.core.transcript_index import invalidate_index

        invalidate_index(path)
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
    # PERF-13-3: 批量写 buffer 命中
    with _BATCH_LOCK:
        if sk in _ACTIVE_BATCHES:
            buf = _BATCH_BUFFERS.setdefault(sk, [])
            buf.append(entry)
            return
    try:
        _append_line(transcript_path(sk), entry)
    except OSError as exc:
        logger.debug("Transcript append skipped: %s", exc)


@contextmanager
def transcript_batch(session_key: str) -> Iterator[None]:
    """PERF-13-3: 批量写上下文。

    with 块内所有 record_*() / append_transcript_entry() 调用走 buffer，
    块退出时一次性 flush（单次 file open + 一次或多次 write）。支持嵌套。
    块外 record_*() 行为不变（立即写）。
    """
    sk = str(session_key or "").strip()
    if not sk:
        yield
        return
    with _BATCH_LOCK:
        _ACTIVE_BATCHES.add(sk)
        _BATCH_BUFFERS.setdefault(sk, [])
    try:
        yield
    finally:
        with _BATCH_LOCK:
            _ACTIVE_BATCHES.discard(sk)
            entries = _BATCH_BUFFERS.pop(sk, [])
        if entries:
            _flush_entries(sk, entries)


def _flush_entries(sk: str, entries: list[dict[str, Any]]) -> None:
    """PERF-13-3: 一次 file open + writelines 写入所有 buffer 条目。"""
    if not entries:
        return
    try:
        path = transcript_path(sk)
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = [json.dumps(e, ensure_ascii=False) + "\n" for e in entries]
        payload_bytes = b"".join(line.encode("utf-8") for line in lines)
        with _LOCK:
            offset = path.stat().st_size if path.is_file() else 0
            with path.open("a", encoding="utf-8") as fh:
                fh.writelines(lines)
            try:
                from butler.core.transcript_index import update_index_after_append

                update_index_after_append(
                    path, line_byte_offset=offset, line_len=len(payload_bytes)
                )
            except Exception as exc:
                logger.debug("append line skipped: %s", exc)
            if path.stat().st_size > transcript_max_bytes():
                _tombstone_tail(path)
    except OSError as exc:
        logger.debug("Transcript batch flush failed: %s", exc)


def record_tool_action(
    session_key: str,
    *,
    tool_name: str,
    args_preview: str = "",
    source: str = "loop",
    tool_call_id: str = "",
) -> None:
    append_transcript_entry(
        session_key,
        "tool_action",
        {
            "tool": str(tool_name or "")[:64],
            "args_preview": str(args_preview or "")[:400],
            "source": str(source or "loop")[:32],
            "tool_call_id": str(tool_call_id or "")[:64],
        },
    )


def record_plan_snapshot(session_key: str, snapshot_json: str) -> None:
    append_transcript_entry(
        session_key,
        "plan_snapshot",
        {
            "snapshot": str(snapshot_json or "")[:8000],
            "source": "workflow",
        },
    )


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


def record_plan_step(
    session_key: str,
    *,
    title: str = "",
    phase: str = "active",
    detail: str = "",
) -> None:
    append_transcript_entry(
        session_key,
        "plan_step",
        {
            "title": (title or "")[:120],
            "phase": str(phase or "active")[:32],
            "detail": (detail or "")[:300],
        },
    )


def record_knowledge_inject(
    session_key: str,
    *,
    source: str = "memory_prefetch",
    chars: int = 0,
) -> None:
    append_transcript_entry(
        session_key,
        "knowledge_inject",
        {
            "source": str(source or "memory")[:32],
            "chars": max(0, int(chars)),
        },
    )


def record_tool_observation(
    session_key: str,
    *,
    tool: str = "",
    tool_name: str = "",
    ok: bool = True,
    outcome: str = "",
    preview: str = "",
    source: str = "loop",
    tool_call_id: str = "",
) -> None:
    name = str(tool_name or tool or "")[:64]
    ok_flag = bool(ok)
    if outcome:
        ok_flag = str(outcome).lower() not in ("error", "fail", "failed")
    append_transcript_entry(
        session_key,
        "tool_observation",
        {
            "tool": name,
            "ok": ok_flag,
            "outcome": str(outcome or ("ok" if ok_flag else "error"))[:16],
            "preview": (preview or "")[:500],
            "source": str(source or "loop")[:32],
            "tool_call_id": str(tool_call_id or "")[:64],
        },
    )


def record_workflow_step(
    session_key: str,
    *,
    workflow: str,
    step_id: str,
    phase: str,
    step_index: int = 0,
    step_total: int = 0,
    error: str = "",
) -> None:
    append_transcript_entry(
        session_key,
        "workflow_step",
        {
            "workflow": workflow,
            "step_id": step_id,
            "phase": phase,
            "step_index": step_index,
            "step_total": step_total,
            "error": (error or "")[:300],
        },
    )


def record_generic_event(session_key: str, event_type: str, payload: dict | None = None) -> None:
    """Append arbitrary audit row (bot_loop_suppressed, etc.)."""
    append_transcript_entry(
        session_key,
        str(event_type or "event"),
        dict(payload or {}),
    )


def record_queue_drop(session_key: str, reason: str, count: int = 1) -> None:
    append_transcript_entry(
        session_key,
        "queue_drop",
        {"reason": str(reason or "?")[:32], "count": max(1, int(count))},
    )


def load_transcript_tail(session_key: str, *, max_lines: int = 50) -> list[dict[str, Any]]:
    path = transcript_path(session_key)
    try:
        from butler.core.transcript_index import load_tail_rows

        return load_tail_rows(path, max_lines=max(1, int(max_lines)))
    except Exception as exc:
        logger.debug("load transcript tail skipped: %s", exc)
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

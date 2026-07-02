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
from butler.env_parse import env_truthy, int_env

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
    return int_env("BUTLER_SESSION_TRANSCRIPT_MAX_BYTES", _DEFAULT_MAX_BYTES, min=1_000_000)


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
        try:
            from butler.core.transcript_fts import index_transcript_line

            line_no = 0
            with path.open(encoding="utf-8") as fh:
                for line_no, _ in enumerate(fh, start=1):
                    pass
            index_transcript_line(path.parent.name, line_no=line_no, entry=entry)
        except Exception as exc:
            logger.debug("transcript FTS append skipped: %s", exc)
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


def record_session_reset(session_key: str, *, reason: str = "new") -> None:
    """Mark a /new (or equivalent) boundary — tool-truth indexes only read rows after this."""
    append_transcript_entry(
        session_key,
        "session_reset",
        {"reason": str(reason or "new")[:32]},
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


def record_compact_started(
    session_key: str,
    *,
    source: str = "context",
    trigger: str = "threshold",
) -> None:
    append_transcript_entry(
        session_key,
        "compact_started",
        {
            "source": str(source or "context")[:32],
            "trigger": str(trigger or "threshold")[:32],
        },
    )


def record_compact_failed(
    session_key: str,
    *,
    source: str = "context",
    reason: str = "unknown",
    iteration: int = 0,
) -> None:
    append_transcript_entry(
        session_key,
        "compact_failed",
        {
            "source": str(source or "context")[:32],
            "reason": str(reason or "unknown")[:64],
            "iteration": max(0, int(iteration)),
        },
    )


def record_overflow_replay(
    session_key: str,
    *,
    source: str = "context_compressor",
    content_preview: str = "",
    replayed_chars: int = 0,
) -> None:
    append_transcript_entry(
        session_key,
        "overflow_replay",
        {
            "source": str(source or "context_compressor")[:32],
            "content_preview": str(content_preview or "")[:80],
            "replayed_chars": max(0, int(replayed_chars)),
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
    assumption: str = "",
    evidence: str = "",
    step_kind: str = "",
) -> None:
    append_transcript_entry(
        session_key,
        "plan_step",
        {
            "title": (title or "")[:120],
            "phase": str(phase or "active")[:32],
            "detail": (detail or "")[:300],
            "assumption": (assumption or "")[:300],
            "evidence": (evidence or "")[:300],
            "step_kind": str(step_kind or "")[:32],
        },
    )
    try:
        from butler.core.reasoning_trace import maybe_sync_plan_step_to_graph

        maybe_sync_plan_step_to_graph(
            session_key,
            title=title,
            step_kind=step_kind,
            assumption=assumption,
            evidence=evidence,
            detail=detail,
        )
    except Exception as exc:
        logger.debug("plan step graph sync skipped: %s", exc)


def record_reasoning_step(
    session_key: str,
    *,
    phase: str = "llm",
    summary: str = "",
    tool_intent: str = "",
    iteration: int = 0,
    source: str = "loop",
) -> None:
    append_transcript_entry(
        session_key,
        "reasoning_step",
        {
            "phase": str(phase or "llm")[:32],
            "summary": (summary or "")[:280],
            "tool_intent": (tool_intent or "")[:120],
            "iteration": max(0, int(iteration)),
            "source": str(source or "loop")[:32],
        },
    )


def record_reflect_step(
    session_key: str,
    *,
    trigger: str = "verify_fail",
    cause: str = "",
    strategy: str = "",
    detail: str = "",
    source: str = "delegate",
) -> None:
    append_transcript_entry(
        session_key,
        "reflect_step",
        {
            "trigger": str(trigger or "verify_fail")[:32],
            "cause": (cause or "")[:200],
            "strategy": (strategy or "")[:64],
            "detail": (detail or "")[:200],
            "source": str(source or "delegate")[:32],
        },
    )


def record_reason_graph_event(
    session_key: str,
    *,
    action: str = "node_added",
    node_id: str = "",
    role: str = "",
    preview: str = "",
) -> None:
    append_transcript_entry(
        session_key,
        "reason_graph",
        {
            "action": str(action or "node_added")[:32],
            "node_id": str(node_id or "")[:16],
            "role": str(role or "")[:32],
            "preview": (preview or "")[:120],
        },
    )


def record_knowledge_inject(
    session_key: str,
    *,
    source: str = "memory_prefetch",
    chars: int = 0,
    terms: list[str] | None = None,
) -> None:
    payload: dict[str, Any] = {
        "source": str(source or "memory")[:32],
        "chars": max(0, int(chars)),
    }
    if terms:
        payload["terms"] = [str(t)[:80] for t in terms if str(t).strip()][:12]
    append_transcript_entry(
        session_key,
        "knowledge_inject",
        payload,
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
    return _load_transcript_lines_from_path(path, max_lines=max_lines)


def reasoning_diag_scan_lines() -> int:
    return int_env("BUTLER_REASONING_DIAG_SCAN_LINES", 2000, min=80)


def _load_transcript_lines_from_path(path: Path, *, max_lines: int) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    try:
        from butler.core.transcript_index import _load_tail_full_read

        return _load_tail_full_read(path, max_lines=max(1, int(max_lines)))
    except Exception:
        pass
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out: list[dict[str, Any]] = []
    for ln in lines[-max(1, int(max_lines)):]:
        try:
            row = json.loads(ln)
            if isinstance(row, dict):
                out.append(row)
        except json.JSONDecodeError:
            continue
    return out


def find_last_transcript_types(
    session_key: str,
    types: frozenset[str],
    *,
    max_scan_lines: int | None = None,
) -> tuple[dict[str, dict[str, Any]], dict[str, int]]:
    """Scan recent transcript from EOF; return newest row per type + counts."""
    limit = reasoning_diag_scan_lines() if max_scan_lines is None else max(1, int(max_scan_lines))
    rows = _load_transcript_lines_from_path(transcript_path(session_key), max_lines=limit)
    counts = {t: 0 for t in types}
    last_by_type: dict[str, dict[str, Any]] = {}
    for row in rows:
        t = str(row.get("type") or "")
        if t not in types:
            continue
        counts[t] = counts.get(t, 0) + 1
        last_by_type[t] = row
    return last_by_type, counts

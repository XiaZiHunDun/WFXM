"""Compaction before/after sampling audit from session transcripts (P5)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_COMPACT_TYPES = frozenset({
    "compact_scheduled",
    "compact_started",
    "compact_done",
    "compact_failed",
    "compact_boundary",
})


@dataclass(frozen=True)
class CompactionAuditSample:
    session_key: str
    ts: str
    event_type: str
    source: str
    tokens_before: int | None
    tokens_after: int | None
    messages_before: int | None
    messages_after: int | None
    summary_chars: int | None
    token_reduction_pct: float | None
    checkpoint_preview_len: int | None
    note: str = ""


def _int_field(row: dict[str, Any], key: str) -> int | None:
    val = row.get(key)
    if val is None:
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def _row_to_sample(session_key: str, row: dict[str, Any], *, pending_before: dict[str, Any] | None) -> CompactionAuditSample:
    event_type = str(row.get("type") or "")
    ts = str(row.get("ts") or "")
    source = str(row.get("source") or "context")
    tokens_before = _int_field(row, "tokens_estimated")
    messages_before = _int_field(row, "messages_before")
    tokens_after = _int_field(row, "tokens_after")
    messages_after = _int_field(row, "messages_after")
    summary_chars = _int_field(row, "summary_chars")

    if pending_before and event_type == "compact_done":
        if tokens_before is None:
            tokens_before = _int_field(pending_before, "tokens_estimated")
        if messages_before is None:
            messages_before = _int_field(pending_before, "messages_before")

    reduction: float | None = None
    if tokens_before and tokens_after is not None and tokens_before > 0:
        reduction = max(0.0, min(100.0, (1.0 - tokens_after / tokens_before) * 100.0))

    ckpt_len: int | None = None
    if event_type == "compact_done":
        try:
            from butler.core.compaction_checkpoint import load_checkpoint

            ckpt = load_checkpoint(session_key)
            if isinstance(ckpt, dict):
                preview = str(ckpt.get("compression_summary_preview") or "")
                ckpt_len = len(preview) if preview else None
        except Exception:
            ckpt_len = None

    note = ""
    if event_type == "compact_failed":
        note = str(row.get("reason") or "failed")[:80]

    return CompactionAuditSample(
        session_key=session_key,
        ts=ts,
        event_type=event_type,
        source=source,
        tokens_before=tokens_before,
        tokens_after=tokens_after,
        messages_before=messages_before,
        messages_after=messages_after,
        summary_chars=summary_chars,
        token_reduction_pct=reduction,
        checkpoint_preview_len=ckpt_len,
        note=note,
    )


def collect_compaction_samples(
    session_key: str,
    *,
    max_events: int = 20,
) -> list[CompactionAuditSample]:
    """Return recent compaction-related transcript rows for one session."""
    from butler.core.session_epoch import load_epoch_transcript_rows

    rows = load_epoch_transcript_rows(session_key, max_lines=500)
    pending: dict[str, Any] | None = None
    out: list[CompactionAuditSample] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        et = str(row.get("type") or "")
        if et not in _COMPACT_TYPES:
            continue
        if et == "compact_scheduled":
            pending = row
        sample = _row_to_sample(session_key, row, pending_before=pending)
        out.append(sample)
        if et == "compact_done":
            pending = None
    return out[-max(1, max_events) :]


def discover_sessions_with_compaction(*, limit: int = 8) -> list[str]:
    """Scan transcript dirs for sessions that have compact_done events."""
    try:
        from butler.config import get_butler_home
        from butler.core.session_transcript import transcript_path
    except Exception:
        return []

    root = get_butler_home() / "sessions"
    if not root.is_dir():
        return []

    found: list[tuple[str, str]] = []
    for child in sorted(root.iterdir(), key=lambda p: p.stat().st_mtime if p.is_dir() else 0, reverse=True):
        if not child.is_dir():
            continue
        tpath = child / "transcript.jsonl"
        if not tpath.is_file():
            continue
        safe = child.name
        try:
            tail = tpath.read_text(encoding="utf-8").splitlines()[-80:]
        except OSError:
            continue
        has_compact = False
        last_ts = ""
        for line in tail:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if str(row.get("type") or "") == "compact_done":
                has_compact = True
                last_ts = str(row.get("ts") or last_ts)
        if has_compact:
            found.append((last_ts, safe))
        if len(found) >= limit:
            break
    found.sort(reverse=True)
    return [sk for _ts, sk in found]


def format_sample_line(sample: CompactionAuditSample) -> str:
    parts = [f"{sample.event_type}@{sample.ts[:19]}", f"src={sample.source}"]
    if sample.tokens_before is not None and sample.tokens_after is not None:
        pct = f"{sample.token_reduction_pct:.0f}%" if sample.token_reduction_pct is not None else "?"
        parts.append(f"tokens {sample.tokens_before}→{sample.tokens_after} (-{pct})")
    elif sample.tokens_before is not None:
        parts.append(f"tokens≈{sample.tokens_before}")
    elif sample.tokens_after is not None:
        parts.append(f"tokens≈{sample.tokens_after}")
    if sample.messages_before is not None and sample.messages_after is not None:
        parts.append(f"msgs {sample.messages_before}→{sample.messages_after}")
    if sample.summary_chars:
        parts.append(f"summary {sample.summary_chars}字")
    if sample.checkpoint_preview_len:
        parts.append(f"ckpt {sample.checkpoint_preview_len}字")
    if sample.note:
        parts.append(sample.note)
    return " | ".join(parts)


def format_audit_report(
    session_key: str,
    samples: list[CompactionAuditSample],
) -> str:
    lines = [f"## 压缩审计 · {session_key}", f"事件数: {len(samples)}"]
    if not samples:
        lines.append("（无 compact_* transcript 事件）")
        return "\n".join(lines)
    for s in samples:
        lines.append(f"- {format_sample_line(s)}")
    return "\n".join(lines)


def run_audit(
    session_key: str | None = None,
    *,
    max_sessions: int = 3,
    max_events: int = 10,
) -> str:
    """Sample compaction audit across one or more sessions."""
    keys: list[str]
    if session_key:
        keys = [session_key.strip()]
    else:
        keys = discover_sessions_with_compaction(limit=max_sessions)
    if not keys:
        return "无含 compact_done 的会话 transcript（需 BUTLER_TRANSCRIPT=1 且曾压缩）。"

    blocks: list[str] = []
    for sk in keys:
        samples = collect_compaction_samples(sk, max_events=max_events)
        blocks.append(format_audit_report(sk, samples))
    return "\n\n".join(blocks)


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Compaction transcript sampling audit")
    parser.add_argument("session_key", nargs="?", default="", help="Optional session key")
    parser.add_argument("--max-sessions", type=int, default=3)
    parser.add_argument("--max-events", type=int, default=10)
    ns = parser.parse_args(argv)
    sk = str(ns.session_key or "").strip() or None
    print(run_audit(sk, max_sessions=ns.max_sessions, max_events=ns.max_events))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

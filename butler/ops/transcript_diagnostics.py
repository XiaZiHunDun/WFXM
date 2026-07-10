"""Transcript JSONL vs FTS index drift diagnostics + /诊断 aggregator."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from butler.config import get_butler_home
from butler.core.transcript_fts import fts_db_path, fts_enabled


def count_jsonl_lines(*, session_key: str = "") -> int:
    """Count non-empty lines across session transcript.jsonl files."""
    root = get_butler_home() / "sessions"
    if not root.is_dir():
        return 0
    sk = str(session_key or "").strip()
    total = 0
    if sk:
        paths = [root / sk / "transcript.jsonl"]
    else:
        paths = [child / "transcript.jsonl" for child in root.iterdir() if child.is_dir()]
    for path in paths:
        if not path.is_file():
            continue
        try:
            for ln in path.read_text(encoding="utf-8").splitlines():
                if ln.strip():
                    total += 1
        except OSError:
            continue
    return total


def count_fts_meta_rows(*, session_key: str = "") -> int:
    """Count rows in transcript_meta (indexed transcript lines)."""
    if not fts_enabled():
        return 0
    db = fts_db_path()
    if not db.is_file():
        return 0
    try:
        conn = sqlite3.connect(str(db))
        sk = str(session_key or "").strip()
        if sk:
            row = conn.execute(
                "SELECT COUNT(*) FROM transcript_meta WHERE session_key = ?",
                (sk,),
            ).fetchone()
        else:
            row = conn.execute("SELECT COUNT(*) FROM transcript_meta")
        conn.close()
        return int(row[0]) if row else 0
    except sqlite3.Error:
        return 0


def transcript_fts_drift(*, session_key: str = "") -> dict[str, Any]:
    """Compare jsonl line count vs FTS meta rows."""
    jsonl_lines = count_jsonl_lines(session_key=session_key)
    fts_rows = count_fts_meta_rows(session_key=session_key)
    gap = max(0, jsonl_lines - fts_rows)
    ratio = (fts_rows / jsonl_lines) if jsonl_lines > 0 else 1.0
    stale = False
    if jsonl_lines > 0 and fts_enabled():
        stale = gap >= 10 or ratio < 0.9
    return {
        "transcript_jsonl_lines": jsonl_lines,
        "transcript_fts_rows": fts_rows,
        "transcript_fts_gap": gap,
        "transcript_fts_stale": stale,
        "transcript_fts_ratio": round(ratio, 3),
        "fts_enabled": fts_enabled(),
    }


def format_transcript_drift_lines(*, session_key: str = "") -> list[str]:
    """Human-readable drift summary for /诊断."""
    drift = transcript_fts_drift(session_key=session_key)
    if not drift.get("fts_enabled"):
        return ["  Transcript FTS: 关 (BUTLER_TRANSCRIPT_FTS=0)"]
    jl = int(drift.get("transcript_jsonl_lines") or 0)
    ft = int(drift.get("transcript_fts_rows") or 0)
    line = f"  Transcript 索引: jsonl {jl} 行 / FTS {ft} 行"
    if drift.get("transcript_fts_stale"):
        line += " — 陈旧，建议 butler transcript index --rebuild"
    return [line]


_COMPACT_KEYS: tuple[str, ...] = (
    "compact_scheduled",
    "compact_started",
    "compact_done",
    "compact_failed",
    "compact_boundary",
    "overflow_replay",
)


def summarize_compact_events(rows: list[dict[str, Any]] | None) -> dict[str, int]:
    """Count compact + overflow_replay transcript rows by type."""
    out: dict[str, int] = {k: 0 for k in _COMPACT_KEYS}
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        t = str(row.get("type") or "")
        if t in out:
            out[t] += 1
    return out


def _load_recent_transcript_rows(session_key: str, *, max_lines: int = 2000) -> list[dict[str, Any]]:
    """Best-effort recent transcript rows for diagnostics (no indexing path assumed)."""
    if not session_key:
        return []
    from butler.core.session_transcript import transcript_path

    path = transcript_path(str(session_key))
    if not path.is_file():
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    out: list[dict[str, Any]] = []
    for ln in text.splitlines()[-max(1, int(max_lines)):]:
        if not ln.strip():
            continue
        try:
            row = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            out.append(row)
    return out


def _compact_line(summary: dict[str, int]) -> str | None:
    if not any(int(summary.get(k) or 0) for k in _COMPACT_KEYS):
        return None
    done = int(summary.get("compact_done") or 0)
    started = int(summary.get("compact_started") or 0)
    scheduled = int(summary.get("compact_scheduled") or 0)
    failed = int(summary.get("compact_failed") or 0)
    boundary = int(summary.get("compact_boundary") or 0)
    overflow = int(summary.get("overflow_replay") or 0)
    parts: list[str] = [
        f"scheduled={scheduled}",
        f"started={started}",
        f"done={done}",
        f"failed={failed}",
        f"boundary={boundary}",
    ]
    if overflow > 0:
        parts.append(f"overflow_replay={overflow}")
    return f"Transcript: 压缩 {done}/{started} 完成 · " + " · ".join(parts)


def _overflow_warn_line(summary: dict[str, int]) -> str | None:
    n = int(summary.get("overflow_replay") or 0)
    if n <= 0:
        return None
    return f"  ⚠️ 续跑提示: 近窗 {n} 次 overflow_replay (上下文压缩后已自动续跑)"


def _reasoning_summary_line(rows: list[dict[str, Any]]) -> str | None:
    n_reason = sum(1 for r in rows if isinstance(r, dict) and r.get("type") == "reasoning_step")
    n_reflect = sum(1 for r in rows if isinstance(r, dict) and r.get("type") == "reflect_step")
    if not n_reason and not n_reflect:
        return None
    return f"  推理摘要: 近窗 reasoning={n_reason} reflect={n_reflect}"


def format_transcript_diagnostic_lines(session_key: str = "", *args: Any, **kwargs: Any) -> list[str]:
    """Aggregate /诊断 transcript surfaces: 压缩 / 续跑 / 推理 / FTS 索引."""
    sk = str(session_key or "").strip()
    rows = _load_recent_transcript_rows(sk)
    summary = summarize_compact_events(rows)
    lines: list[str] = []
    cl = _compact_line(summary)
    if cl:
        lines.append(cl)
    ow = _overflow_warn_line(summary)
    if ow:
        lines.append(ow)
    rs = _reasoning_summary_line(rows)
    if rs:
        lines.append(rs)
    lines.extend(format_transcript_drift_lines(session_key=sk))
    return lines


__all__ = [
    "count_fts_meta_rows",
    "count_jsonl_lines",
    "format_transcript_diagnostic_lines",
    "format_transcript_drift_lines",
    "summarize_compact_events",
    "transcript_fts_drift",
]
"""Transcript JSONL vs FTS index drift diagnostics."""

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
            row = conn.execute("SELECT COUNT(*) FROM transcript_meta").fetchone()
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


__all__ = [
    "count_fts_meta_rows",
    "count_jsonl_lines",
    "format_transcript_drift_lines",
    "transcript_fts_drift",
]

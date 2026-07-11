"""SQLite FTS5 index for session transcript search."""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any

from butler.config import get_butler_home
from butler.env_parse import env_truthy

logger = logging.getLogger(__name__)

_LOCK = threading.RLock()
_CONN: sqlite3.Connection | None = None
_CONN_PATH: Path | None = None


def reset_transcript_fts_connection() -> None:
    """Close + drop the module-level cached FTS connection (test isolation hook).

    Used by autouse fixtures that swap ``BUTLER_HOME`` so the cached
    connection — which is bound to a specific ``fts_db_path()`` — doesn't
    leak between tests pointing at different homes.
    """
    global _CONN, _CONN_PATH
    with _LOCK:
        if _CONN is not None:
            try:
                _CONN.close()
            except sqlite3.Error:
                pass
        _CONN = None
        _CONN_PATH = None

_CRON_SESSION_RE = re.compile(r"(?:^|[_/])cron(?:[_/]|$)", re.I)


def fts_enabled() -> bool:
    return bool(env_truthy("BUTLER_TRANSCRIPT_FTS", default=True))
def fts_db_path() -> Path:
    return Path(get_butler_home()) / "transcript_fts.db"


def cron_deprioritize_enabled() -> bool:
    return bool(env_truthy("BUTLER_TRANSCRIPT_FTS_DEPRIORITIZE_CRON", default=True))
def _is_cron_session(session_key: str) -> bool:
    return bool(_CRON_SESSION_RE.search(str(session_key or "")))


def _connect() -> sqlite3.Connection:
    global _CONN, _CONN_PATH
    with _LOCK:
        path = fts_db_path()
        if _CONN is not None and _CONN_PATH == path:
            return _CONN
        if _CONN is not None:
            # Path changed (BUTLER_HOME swap) — drop stale connection.
            try:
                _CONN.close()
            except sqlite3.Error:
                pass
            _CONN = None
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS transcript_meta (
                session_key TEXT NOT NULL,
                line_no INTEGER NOT NULL,
                event_type TEXT NOT NULL DEFAULT '',
                body TEXT NOT NULL,
                PRIMARY KEY (session_key, line_no)
            );
            CREATE VIRTUAL TABLE IF NOT EXISTS transcript_fts USING fts5(
                session_key,
                line_no UNINDEXED,
                event_type,
                body
            );
            """
        )
        _CONN = conn
        _CONN_PATH = path
        return conn


def _extract_body(entry: dict[str, Any]) -> str:
    for key in ("content_preview", "preview", "content", "summary"):
        val = entry.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()[:4000]
    try:
        return json.dumps(
            {k: v for k, v in entry.items() if k not in ("ts",)},
            ensure_ascii=False,
        )[:4000]
    except TypeError:
        return str(entry)[:4000]


def index_transcript_line(
    session_key: str,
    *,
    line_no: int,
    entry: dict[str, Any],
) -> None:
    if not fts_enabled():
        return
    body = _extract_body(entry)
    if not body.strip():
        return
    event_type = str(entry.get("type") or "")
    sk = str(session_key or "")
    try:
        conn = _connect()
        with _LOCK:
            conn.execute(
                "DELETE FROM transcript_meta WHERE session_key = ? AND line_no = ?",
                (sk, line_no),
            )
            conn.execute(
                "INSERT INTO transcript_meta (session_key, line_no, event_type, body) "
                "VALUES (?, ?, ?, ?)",
                (sk, line_no, event_type, body),
            )
            conn.execute(
                "DELETE FROM transcript_fts WHERE session_key = ? AND line_no = ?",
                (sk, line_no),
            )
            conn.execute(
                "INSERT INTO transcript_fts (session_key, line_no, event_type, body) "
                "VALUES (?, ?, ?, ?)",
                (sk, line_no, event_type, body),
            )
            conn.commit()
    except sqlite3.Error as exc:
        logger.debug("transcript FTS index skipped: %s", exc)


def index_transcript_file(transcript_jsonl: Path, *, session_key: str | None = None) -> int:
    if not transcript_jsonl.is_file():
        return 0
    sk = session_key or transcript_jsonl.parent.name
    count = 0
    try:
        lines = transcript_jsonl.read_text(encoding="utf-8").splitlines()
    except OSError:
        return 0
    for idx, ln in enumerate(lines, start=1):
        try:
            row = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            index_transcript_line(sk, line_no=idx, entry=row)
            count += 1
    return count


def rebuild_all_transcripts() -> dict[str, int]:
    root = get_butler_home() / "sessions"
    stats: dict[str, int] = {"sessions": 0, "lines": 0}
    if not root.is_dir():
        return stats
    try:
        conn = _connect()
        with _LOCK:
            conn.execute("DELETE FROM transcript_meta")
            conn.execute("DELETE FROM transcript_fts")
            conn.commit()
    except sqlite3.Error as exc:
        logger.warning("FTS rebuild clear failed: %s", exc)
        return stats
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        tpath = child / "transcript.jsonl"
        if not tpath.is_file():
            continue
        n = index_transcript_file(tpath, session_key=child.name)
        if n:
            stats["sessions"] += 1
            stats["lines"] += n
    return stats


def search_fts(
    query: str,
    *,
    session_key: str = "",
    limit: int = 15,
    offset: int = 0,
) -> list[dict[str, Any]]:
    if not fts_enabled():
        return []
    q = (query or "").strip()
    if len(q) < 2:
        return []
    fts_query = " ".join(f'"{part}"' for part in q.split() if part)
    if not fts_query:
        return []
    try:
        conn = _connect()
        params: list[Any] = [fts_query]
        where = "transcript_fts MATCH ?"
        if session_key.strip():
            where += " AND session_key = ?"
            params.append(session_key.strip())
        sql = (
            "SELECT session_key, line_no, event_type, "
            "snippet(transcript_fts, 3, '', '', '…', 32) AS snip "
            f"FROM transcript_fts WHERE {where} "
            "ORDER BY rank LIMIT ? OFFSET ?"
        )
        fetch_limit = max(1, limit) * 4
        params.extend([fetch_limit, max(0, offset)])
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.Error as exc:
        logger.debug("transcript FTS search failed: %s", exc)
        return []

    hits: list[dict[str, Any]] = []
    cap = max(1, limit)
    for row in rows:
        sk = str(row["session_key"])
        weight = 0.5 if cron_deprioritize_enabled() and _is_cron_session(sk) else 1.0
        preview = str(row["snip"] or "")[:200]
        hits.append({
            "session_key": sk,
            "line": int(row["line_no"]),
            "type": row["event_type"] or "?",
            "preview": preview,
            "_weight": weight,
        })
    if cron_deprioritize_enabled():
        hits.sort(key=lambda h: (-float(h.get("_weight", 1.0)), h.get("line", 0)))
    for h in hits:
        h.pop("_weight", None)
    return hits[:cap]


__all__ = [
    "cron_deprioritize_enabled",
    "fts_enabled",
    "index_transcript_file",
    "index_transcript_line",
    "rebuild_all_transcripts",
    "reset_transcript_fts_connection",
    "search_fts",
]

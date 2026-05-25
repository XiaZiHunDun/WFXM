"""CLI: ``butler sessions list [--search]``."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console
from rich.table import Table


def _sessions_root() -> Path:
    from butler.config import get_butler_home

    return get_butler_home() / "sessions"


def list_sessions(*, search: str = "", limit: int = 20) -> list[dict]:
    root = _sessions_root()
    if not root.is_dir():
        return []
    q = (search or "").strip().lower()
    lim = max(1, min(100, int(limit or 20)))
    rows: list[dict] = []

    for child in sorted(root.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if not child.is_dir():
            continue
        session_key = child.name
        if q and q not in session_key.lower():
            continue
        transcript = child / "transcript.jsonl"
        mtime = child.stat().st_mtime
        line_count = 0
        last_type = ""
        if transcript.is_file():
            try:
                mtime = transcript.stat().st_mtime
                with transcript.open(encoding="utf-8") as fh:
                    for line in fh:
                        line = line.strip()
                        if not line:
                            continue
                        line_count += 1
                        try:
                            row = json.loads(line)
                            last_type = str(row.get("type") or "")
                        except json.JSONDecodeError:
                            pass
            except OSError:
                pass
        rows.append(
            {
                "session_key": session_key,
                "transcript_lines": line_count,
                "last_event_type": last_type,
                "updated_at": datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat(),
                "path": str(transcript),
            }
        )
        if len(rows) >= lim:
            break
    return rows


def _cmd_sessions_list(ns: argparse.Namespace) -> int:
    console = Console()
    rows = list_sessions(search=str(ns.search or ""), limit=int(ns.limit or 20))
    if not rows:
        console.print("[dim]无会话记录（~/.butler/sessions/）[/dim]")
        return 0
    table = Table(title="Butler 会话")
    table.add_column("session_key")
    table.add_column("lines", justify="right")
    table.add_column("last_event")
    table.add_column("updated")
    for row in rows:
        table.add_row(
            row["session_key"],
            str(row["transcript_lines"]),
            row.get("last_event_type") or "-",
            (row.get("updated_at") or "")[:19],
        )
    console.print(table)
    return 0


def register_sessions_subparser(sub: argparse._SubParsersAction) -> None:
    sess = sub.add_parser("sessions", help="会话 transcript 列表")
    sess_sub = sess.add_subparsers(dest="sessions_cmd", required=True)
    ls = sess_sub.add_parser("list", help="列出最近会话")
    ls.add_argument("--search", default="", help="过滤 session_key")
    ls.add_argument("--limit", type=int, default=20)
    ls.set_defaults(func=_cmd_sessions_list)

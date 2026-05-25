"""Search session transcript JSONL (Hermes session_search subset)."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from butler.core.session_transcript import transcript_enabled, transcript_path


def search_max_sessions() -> int:
    try:
        return max(1, min(20, int(os.getenv("BUTLER_TRANSCRIPT_SEARCH_MAX_SESSIONS", "5"))))
    except ValueError:
        return 5


def search_max_hits() -> int:
    try:
        return max(1, min(50, int(os.getenv("BUTLER_TRANSCRIPT_SEARCH_MAX_HITS", "15"))))
    except ValueError:
        return 15


def _sessions_root() -> Path:
    from butler.config import get_butler_home

    return get_butler_home() / "sessions"


def _iter_session_transcripts(
    *,
    session_key: str = "",
    limit_sessions: int | None = None,
) -> list[tuple[str, Path]]:
    root = _sessions_root()
    if not root.is_dir():
        return []
    out: list[tuple[str, Path]] = []
    if session_key.strip():
        path = transcript_path(session_key)
        if path.is_file():
            return [(session_key, path)]
        return []

    cap = limit_sessions if limit_sessions is not None else search_max_sessions()
    dirs = sorted(root.iterdir(), key=lambda p: p.stat().st_mtime if p.is_dir() else 0, reverse=True)
    for d in dirs:
        if not d.is_dir():
            continue
        tpath = d / "transcript.jsonl"
        if tpath.is_file():
            out.append((d.name, tpath))
        if len(out) >= cap:
            break
    return out


def search_transcripts(
    query: str,
    *,
    session_key: str = "",
    max_hits: int | None = None,
) -> list[dict[str, Any]]:
    if not transcript_enabled():
        return []
    q = (query or "").strip().lower()
    if len(q) < 2:
        return []
    pattern = re.compile(re.escape(q), re.IGNORECASE)
    hits: list[dict[str, Any]] = []
    cap = max_hits if max_hits is not None else search_max_hits()

    for sk, path in _iter_session_transcripts(session_key=session_key):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for idx, ln in enumerate(lines):
            if not pattern.search(ln):
                continue
            try:
                row = json.loads(ln)
            except json.JSONDecodeError:
                row = {"raw": ln[:300]}
            preview = ""
            if isinstance(row, dict):
                preview = str(row.get("content_preview") or row.get("preview") or "")[:200]
                if not preview:
                    preview = json.dumps(
                        {k: v for k, v in row.items() if k not in ("ts",)},
                        ensure_ascii=False,
                    )[:200]
            hits.append({
                "session_key": sk,
                "line": idx + 1,
                "type": row.get("type") if isinstance(row, dict) else "?",
                "preview": preview,
            })
            if len(hits) >= cap:
                return hits
    return hits


def register_transcript_search_tool(register_fn) -> None:
    """Register Hermes-style session transcript search."""

    def _handler(args: dict) -> str:
        import json

        from butler.execution_context import get_current_session_key

        query = str(args.get("query") or "").strip()
        sk = str(args.get("session_key") or get_current_session_key() or "").strip()
        max_hits = args.get("max_hits")
        try:
            cap = int(max_hits) if max_hits is not None else None
        except (TypeError, ValueError):
            cap = None
        hits = search_transcripts(query, session_key=sk, max_hits=cap)
        return json.dumps({"hits": hits, "count": len(hits)}, ensure_ascii=False)

    register_fn(
        name="search_transcript",
        description=(
            "Search session transcript JSONL for keywords (current or recent sessions). "
            "Requires BUTLER_SESSION_TRANSCRIPT=1."
        ),
        schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search keyword (min 2 chars)"},
                "session_key": {
                    "type": "string",
                    "description": "Optional session key; default current session",
                },
                "max_hits": {"type": "integer", "description": "Max results (default from env)"},
            },
            "required": ["query"],
        },
        handler=_handler,
        toolset="memory",
    )

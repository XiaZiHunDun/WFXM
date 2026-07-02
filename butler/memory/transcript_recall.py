"""Search session transcripts via ``butler_recall`` / ``butler memory search`` (P3-H phase 2)."""

from __future__ import annotations

import json
from typing import Any


def search_transcript_recall(
    query: str,
    *,
    session_key: str = "",
    limit: int = 8,
    offset: int = 0,
) -> dict[str, Any]:
    """Keyword / FTS search over session transcript JSONL (thin wrapper over ``transcript_search``)."""
    q = str(query or "").strip()
    if len(q) < 2:
        return {"ok": False, "error": "query is required (≥2 chars)"}

    from butler.core.session_transcript import transcript_enabled

    if not transcript_enabled():
        return {
            "ok": False,
            "error": "BUTLER_SESSION_TRANSCRIPT=0; transcript recall unavailable",
        }

    from butler.core.transcript_fts import fts_enabled
    from butler.core.transcript_search import search_transcripts

    lim = max(1, min(50, int(limit or 8)))
    off = max(0, int(offset or 0))
    sk = str(session_key or "").strip()

    hits = search_transcripts(q, session_key=sk, max_hits=lim, offset=off)
    mode = "transcript-fts" if fts_enabled() else "transcript-scan"

    try:
        from butler.execution_context import get_current_session_key
        from butler.memory.retrieval_telemetry import record_last_retrieval

        tel_sk = sk or get_current_session_key() or ""
        if tel_sk:
            record_last_retrieval(
                tel_sk,
                {
                    "mode": mode,
                    "fallbacks": 0,
                    "candidates": len(hits),
                    "query": q,
                    "scope": "transcript",
                },
            )
    except Exception:
        pass

    return {
        "ok": True,
        "scope": "transcript",
        "query": q,
        "mode": mode,
        "session_key": sk or None,
        "results": hits,
        "count": len(hits),
    }


def search_transcript_recall_json(**kwargs: Any) -> str:
    return json.dumps(search_transcript_recall(**kwargs), ensure_ascii=False)


__all__ = ["search_transcript_recall", "search_transcript_recall_json"]

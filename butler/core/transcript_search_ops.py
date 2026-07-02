"""Best-effort transcript FTS search (P0-A)."""

from __future__ import annotations

from typing import Any

from butler.core.best_effort import safe_best_effort


def search_transcripts_fts(
    query: str,
    *,
    session_key: str = "",
    limit: int,
    offset: int,
) -> list[dict[str, Any]] | None:
    def _run() -> list[dict[str, Any]] | None:
        from butler.core.transcript_fts import fts_enabled, search_fts

        if not fts_enabled():
            return None
        hits = search_fts(
            query,
            session_key=session_key,
            limit=limit,
            offset=offset,
        )
        return hits if hits else None

    return safe_best_effort(
        _run,
        label="transcript_search.fts",
        default=None,
    )

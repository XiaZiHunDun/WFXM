"""Best-effort helpers for semantic index recall paths (P0-A)."""

from __future__ import annotations

import logging
from typing import Any, Callable

from butler.core.best_effort import safe_best_effort

from butler.memory.triplets import TripletIndex
from butler.memory.query_decompose import (
    decompose_query,
    subquery_enabled,
)
from butler.execution_context import get_current_session_key
from butler.memory.retrieval_telemetry import (
    get_last_retrieval,
    record_last_retrieval,
)
from butler.core.structured_events import emit_retrieval
from butler.memory.vector_sync_telemetry import record_vector_sync

logger = logging.getLogger(__name__)


def close_semantic_index(index: Any) -> None:
    safe_best_effort(
        lambda: index.close(),
        label="semantic_index.shutdown_close",
        default=None,
    )


def fetch_experience_rows_by_ids(store: Any, ids: list[int]) -> dict[int, dict[str, Any]]:
    def _run() -> dict[int, dict[str, Any]]:
        return {int(r["id"]): r for r in store.fetch_by_ids(ids)}

    result = safe_best_effort(
        _run,
        label="semantic_index.enrich_experience_tags",
        default={},
    )
    return result if isinstance(result, dict) else {}


def index_triplets_safe(
    semantic: Any,
    content: str,
    *,
    project: str,
    source: str,
    source_ref: str,
) -> int:
    def _run() -> int:

        return TripletIndex(semantic.db_path).upsert_from_content(
            content=content,
            project=project,
            source=source,
            source_ref=source_ref,
        )

    result = safe_best_effort(
        _run,
        label="semantic_index.triplets",
        default=0,
    )
    return int(result) if isinstance(result, int) else 0


def subquery_enabled_for(query: str) -> bool:
    def _run() -> bool:

        return bool(subquery_enabled() and len(decompose_query(query)) > 1)

    return safe_best_effort(
        _run,
        label="semantic_index.subquery_gate",
        default=False,
    ) is True


def record_relaxation_note(query: str) -> None:
    def _run() -> None:

        sk = str(get_current_session_key() or "")
        if not sk:
            return
        prev = get_last_retrieval(sk) or {}
        record_last_retrieval(
            sk,
            {
                **prev,
                "relaxation_note": True,
                "query": query,
            },
        )

    safe_best_effort(_run, label="semantic_index.relaxation_note", default=None)


def record_hybrid_recall_telemetry(
    *,
    mode: str,
    fallbacks: int,
    out: list[dict[str, Any]],
    query: str,
    sub_queries: list[str],
    degraded: bool,
) -> None:
    def _run() -> None:
        from butler.memory.semantic_index import _build_recall_telemetry_payload

        sk = str(get_current_session_key() or "")
        record_last_retrieval(
            sk,
            _build_recall_telemetry_payload(
                mode=mode,
                fallbacks=fallbacks,
                out=out,
                q=query,
                sub_queries=sub_queries,
                degraded=degraded,
            ),
        )

        emit_retrieval(
            mode=mode,
            degraded=degraded,
            fallbacks=fallbacks,
            session_key=sk,
        )

    safe_best_effort(_run, label="semantic_index.recall_telemetry", default=None)


def record_experience_access(store: Any, ids: list[int]) -> None:
    def _run() -> None:
        store.record_access(ids)

    safe_best_effort(_run, label="semantic_index.experience_access", default=None)


def run_hybrid_search_relaxed(
    fn: Callable[..., tuple[list[dict[str, Any]], str, int, bool, str | None]],
    *args: Any,
    **kwargs: Any,
) -> tuple[list[dict[str, Any]], str, int, bool, str | None] | None:
    return safe_best_effort(
        lambda: fn(*args, **kwargs),
        label="semantic_index.hybrid_relaxed",
        default=None,
    )


def index_experience_row_loud(
    semantic: Any,
    row_id: int,
    *,
    project: str,
    category: str,
    content: str,
) -> None:
    if semantic is None or not content.strip():
        return
    from butler.memory.semantic_index import (
        SOURCE_EXPERIENCE,
        _CONVERSATION,
        index_triplets_for_content,
    )

    if (category or "") == _CONVERSATION:
        return
    try:
        semantic.upsert(
            source=SOURCE_EXPERIENCE,
            source_id=str(row_id),
            content=content,
            project=project or "",
            category=category or "",
        )
        index_triplets_for_content(
            semantic,
            content,
            project=project or "",
            source=SOURCE_EXPERIENCE,
            source_ref=str(row_id),
        )

        record_vector_sync("owner_experience", project=project or "")
    except Exception as exc:
        # Audit R2-2: preserve stack trace for embed OOM / DB lock / provider auth.
        _fail_loud_logger.error(
            "Semantic index upsert failed for experience %s", row_id, exc_info=exc
        )


def hybrid_experience_search_once_loud(
    semantic: Any,
    fts_search: Callable[..., list[dict[str, Any]]],
    query: str,
    *,
    project: str | None = None,
    limit: int = 8,
) -> tuple[list[dict[str, Any]], str, int, bool]:
    from butler.memory.semantic_index import SOURCE_EXPERIENCE

    fts_hits = fts_search(query, project=project, limit=limit * 2)
    mode = "fts" if semantic is None else "hybrid"
    fallbacks = 0
    degraded = False
    if semantic is None:
        out = fts_hits[:limit]
    else:
        try:
            out = semantic.hybrid_search(
                query,
                fts_hits,
                project=project,
                limit=limit,
                vector_sources=(SOURCE_EXPERIENCE,),
            )
        except Exception as exc:
            _fail_loud_logger.error("Hybrid search failed, using FTS", exc_info=exc)
            out = fts_hits[:limit]
            mode = "fts-error-fallback"
            fallbacks += 1
            degraded = True
    if not out and project is not None:
        fallbacks += 1
        global_fts_hits = fts_search(query, project=None, limit=limit * 4)
        if semantic is None:
            out = global_fts_hits[:limit]
            mode = "fts-fallback-global"
        else:
            try:
                out = semantic.hybrid_search(
                    query,
                    global_fts_hits,
                    project=None,
                    limit=limit,
                    vector_sources=(SOURCE_EXPERIENCE,),
                )
                mode = "hybrid-fallback-global"
            except Exception as exc:
                _fail_loud_logger.error(
                    "Hybrid global fallback failed, using FTS", exc_info=exc
                )
                out = global_fts_hits[:limit]
                mode = "fts-fallback-global"
                degraded = True
    return out, mode, fallbacks, degraded


# R2-2 caplog tests target the semantic_index logger name.
_fail_loud_logger = logging.getLogger("butler.memory.semantic_index")


__all__ = [
    "close_semantic_index",
    "fetch_experience_rows_by_ids",
    "hybrid_experience_search_once_loud",
    "index_experience_row_loud",
    "index_triplets_safe",
    "record_experience_access",
    "record_hybrid_recall_telemetry",
    "record_relaxation_note",
    "run_hybrid_search_relaxed",
    "subquery_enabled_for",
]

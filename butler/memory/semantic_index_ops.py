"""Best-effort helpers for semantic index recall paths (P0-A)."""

from __future__ import annotations

import logging
from typing import Any, Callable

from butler.core.best_effort import safe_best_effort

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
        from butler.memory.triplets import TripletIndex

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
        from butler.memory.query_decompose import decompose_query, subquery_enabled

        return bool(subquery_enabled() and len(decompose_query(query)) > 1)

    return safe_best_effort(
        _run,
        label="semantic_index.subquery_gate",
        default=False,
    ) is True


def record_relaxation_note(query: str) -> None:
    def _run() -> None:
        from butler.execution_context import get_current_session_key
        from butler.memory.retrieval_telemetry import get_last_retrieval, record_last_retrieval

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
        from butler.execution_context import get_current_session_key
        from butler.memory.retrieval_telemetry import record_last_retrieval
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
        from butler.core.structured_events import emit_retrieval

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


__all__ = [
    "close_semantic_index",
    "fetch_experience_rows_by_ids",
    "index_triplets_safe",
    "record_experience_access",
    "record_hybrid_recall_telemetry",
    "record_relaxation_note",
    "run_hybrid_search_relaxed",
    "subquery_enabled_for",
]

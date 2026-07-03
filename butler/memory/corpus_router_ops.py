"""Corpus router query decomposition best-effort helpers (P0-A)."""

from __future__ import annotations

from butler.core.best_effort import safe_best_effort


def decompose_recall_queries_safe(query: str) -> list[str]:
    def _run() -> list[str]:
        from butler.memory.query_decompose import decompose_query, subquery_enabled

        if not subquery_enabled():
            return [query]
        sub_queries = decompose_query(query)
        return list(sub_queries) if sub_queries else [query]

    result = safe_best_effort(
        _run,
        label="corpus_router.decompose",
        default=[query],
    )
    return list(result) if isinstance(result, list) and result else [query]

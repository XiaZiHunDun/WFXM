"""RAG sub-query decomposition and merge (P1)."""

from __future__ import annotations

from butler.memory.query_decompose import (
    decompose_query,
    merge_retrieval_hits,
    search_with_subqueries,
)
from butler.memory.semantic_index import hybrid_experience_search


def test_decompose_splits_compound_question():
    q = "网关队列怎么配？以及 MEMORY 索引如何重建？"
    subs = decompose_query(q)
    assert len(subs) >= 2
    assert any("网关" in s for s in subs)


def test_decompose_short_query_unchanged():
    subs = decompose_query("pytest")
    assert subs == ["pytest"]


def test_merge_dedup_keeps_best_score():
    batches = [
        ("a", [{"source_id": "x", "content": "one", "score": 0.5}]),
        ("b", [{"source_id": "x", "content": "one", "score": 0.9}]),
    ]
    merged = merge_retrieval_hits(batches, limit=5)
    assert len(merged) == 1
    assert merged[0]["score"] == 0.9
    assert merged[0]["score_breakdown"]["matched_subquery"] == "b"


def test_hybrid_experience_search_subquery_merge():
    calls: list[str] = []

    def _fts(query: str, project=None, limit=10):
        calls.append(query)
        return [{"id": 1, "content": f"hit-{query[:8]}", "score": 0.5}]

    out = hybrid_experience_search(
        None,
        _fts,
        "主题 A？另外主题 B 怎么弄",
        project=None,
        limit=4,
    )
    assert out
    assert len(calls) >= 2


def test_search_with_subqueries_limits():
    merged, subs = search_with_subqueries(
        "alpha？以及 beta 配置",
        lambda q: [{"source_id": q, "score": 1.0, "content": q}],
        limit=2,
    )
    assert len(subs) >= 2
    assert len(merged) <= 2

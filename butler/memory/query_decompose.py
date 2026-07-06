"""Lightweight query decomposition for multi-pass retrieval (RAGFlow P1 subset)."""

from __future__ import annotations

import os
import re
from typing import Any, Callable

from butler.env_parse import env_truthy

_SPLIT_RE = re.compile(
    r"[?；;]\s*|以及|另外|同时|还有|\s+and\s+also\s+|\s+and\s+",
    re.IGNORECASE,
)
_MIN_PIECE_LEN = 4
_SENTENCE_RE = re.compile(r"[。！!\n]+")


def subquery_enabled() -> bool:
    return bool(env_truthy("BUTLER_RAG_SUBQUERY", default=True))


def max_subqueries() -> int:
    try:
        from butler.env_parse import int_env

        return int(int_env("BUTLER_RAG_SUBQUERY_MAX", 3, min=1, max=5))
    except ValueError:
        return 3


def min_chars_for_split() -> int:
    try:
        from butler.env_parse import int_env

        return int(int_env("BUTLER_RAG_SUBQUERY_MIN_CHARS", 72, min=40))
    except ValueError:
        return 72


def decompose_query(query: str) -> list[str]:
    """
    Split a compound question into ≤N sub-queries (heuristic, no LLM).

    Always includes the full original query when splitting occurs.
    """
    q = str(query or "").strip()
    if not q:
        return []
    if not subquery_enabled():
        return [q]

    parts: list[str] = []
    for chunk in _SPLIT_RE.split(q):
        piece = chunk.strip()
        if piece and len(piece) >= _MIN_PIECE_LEN:
            parts.append(piece)

    if len(parts) <= 1 and len(q) >= min_chars_for_split():
        for sent in _SENTENCE_RE.split(q):
            piece = sent.strip()
            if piece and len(piece) >= 12:
                parts.append(piece)

    if len(parts) <= 1:
        return [q]

    cap = max_subqueries()
    deduped: list[str] = []
    seen: set[str] = set()
    for candidate in [q, *parts]:
        key = candidate.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(candidate.strip())
        if len(deduped) >= cap:
            break
    return deduped or [q]


def _hit_key(hit: dict[str, Any]) -> str:
    for field in ("source_id", "id", "chunk_id"):
        val = hit.get(field)
        if val is not None and str(val).strip():
            return f"{field}:{val}"
    content = str(hit.get("content") or "").strip()
    return f"content:{content[:120]}" if content else f"row:{id(hit)}"


def merge_retrieval_hits(
    batches: list[tuple[str, list[dict[str, Any]]]],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    """Merge hits from multiple sub-queries; keep best score per key."""
    best: dict[str, dict[str, Any]] = {}
    for sub_q, hits in batches:
        for raw in hits:
            if not isinstance(raw, dict):
                continue
            item = dict(raw)
            key = _hit_key(item)
            score = float(item.get("rank_score") or item.get("score") or 0.0)
            prev = best.get(key)
            if prev is None or score > float(prev.get("rank_score") or prev.get("score") or 0.0):
                breakdown = dict(item.get("score_breakdown") or {})
                breakdown["matched_subquery"] = sub_q[:80]
                item["score_breakdown"] = breakdown
                best[key] = item
    ranked = sorted(
        best.values(),
        key=lambda h: float(h.get("rank_score") or h.get("score") or 0.0),
        reverse=True,
    )
    return ranked[: max(1, limit)]


def search_with_subqueries(
    query: str,
    search_fn: Callable[[str], list[dict[str, Any]]],
    *,
    limit: int,
) -> tuple[list[dict[str, Any]], list[str]]:
    """
    Run *search_fn* per sub-query and merge.

    Returns (merged_hits, sub_queries_used).
    """
    subs = decompose_query(query)
    if len(subs) <= 1:
        return search_fn(query)[:limit], subs
    per = max(limit, (limit * 2 + len(subs) - 1) // len(subs))
    batches: list[tuple[str, list[dict[str, Any]]]] = []
    for sub in subs:
        batches.append((sub, search_fn(sub)[:per]))
    merged = merge_retrieval_hits(batches, limit=limit)
    return merged, subs


__all__ = [
    "decompose_query",
    "max_subqueries",
    "merge_retrieval_hits",
    "search_with_subqueries",
    "subquery_enabled",
]

"""Semantic index health checks (experience ↔ vector drift)."""

from __future__ import annotations

from typing import Any

from butler.session.lifecycle import CONVERSATION_CATEGORY


def experience_vector_drift(
    *,
    experience_long_term: int,
    experience_vectors: int,
) -> dict[str, Any]:
    """Compare indexable experience rows vs experience-source vectors.

    Returns keys: experience_indexable, experience_vectors, semantic_index_gap,
    semantic_index_stale, semantic_index_ratio.
    """
    indexable = max(0, int(experience_long_term or 0))
    vec_exp = max(0, int(experience_vectors or 0))
    gap = max(0, indexable - vec_exp)
    ratio = (vec_exp / indexable) if indexable > 0 else 1.0
    stale = False
    if indexable > 0 and gap > 0:
        stale = gap >= 3 or ratio < 0.85
    return {
        "experience_indexable": indexable,
        "experience_vectors": vec_exp,
        "semantic_index_gap": gap,
        "semantic_index_stale": stale,
        "semantic_index_ratio": round(ratio, 3),
    }


def drift_from_butler_memory(bm: Any) -> dict[str, Any]:
    """Drift report from a ButlerMemory instance (no orchestrator)."""
    from butler.memory.diagnostics import _experience_category_counts
    from butler.memory.semantic_config import semantic_memory_enabled
    from butler.memory.semantic_index import SOURCE_EXPERIENCE

    empty = experience_vector_drift(experience_long_term=0, experience_vectors=0)
    if not semantic_memory_enabled():
        empty["skipped"] = True
        return empty
    sem = getattr(bm, "semantic", None)
    if sem is None:
        empty["skipped"] = True
        return empty
    exp = getattr(bm, "experience", None)
    if exp is None:
        return empty
    by_cat = _experience_category_counts(getattr(exp, "db_path", None))
    indexable = sum(n for k, n in by_cat.items() if k != CONVERSATION_CATEGORY)
    try:
        vec_exp = sem.count_by_source(SOURCE_EXPERIENCE)
    except Exception:
        vec_exp = 0
    report = experience_vector_drift(
        experience_long_term=indexable,
        experience_vectors=vec_exp,
    )
    report["skipped"] = False
    return report

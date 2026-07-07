"""Unified hybrid recall: experience + project + coding with normalized scores (P3-H phase 3)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from butler.memory.query_decompose import merge_retrieval_hits
from butler.memory.unified_recall_config import observation_recall_boost, observation_recall_enabled, unified_recall_enabled, unified_scope_weights
from butler.memory.semantic_index import hybrid_experience_search
from butler.session.lifecycle import filter_non_conversation_experience
from butler.memory.semantic_config import semantic_memory_enabled
from butler.memory.semantic_project import prefetch_project_memory_hits, resolve_project_display_name
from butler.config import get_butler_home
from butler.memory.coding_recall import search_coding_experiences
from butler.memory.observation_recall import search_observation_recall
from butler.memory.recall_ops import record_scope_retrieval_safe


def _normalize_batch(
    hits: list[dict[str, Any]],
    *,
    scope: str,
    weight: float,
) -> list[dict[str, Any]]:
    if not hits:
        return []
    raw_scores = [float(h.get("rank_score") or h.get("score") or 0.0) for h in hits]
    max_s = max(raw_scores)
    min_s = min(raw_scores)
    span = max(max_s - min_s, 1e-6)
    out: list[dict[str, Any]] = []
    for hit, raw in zip(hits, raw_scores):
        item = dict(hit)
        norm = (raw - min_s) / span if span > 1e-6 else 1.0
        unified = round(norm * weight, 6)
        item["recall_scope"] = scope
        item["base_score"] = raw
        item["unified_score"] = unified
        item["score"] = unified
        breakdown = dict(item.get("score_breakdown") or {})
        breakdown.update(
            {
                "scope": scope,
                "scope_weight": weight,
                "normalized": round(norm, 4),
                "unified_score": unified,
            }
        )
        item["score_breakdown"] = breakdown
        out.append(item)
    return out


def _path_text(hit: dict[str, Any]) -> str:
    parts = [
        str(hit.get("source_path") or ""),
        str(hit.get("path") or ""),
        str(hit.get("content") or ""),
        str(hit.get("pattern") or ""),
        str(hit.get("section") or ""),
    ]
    return " ".join(parts).lower()


def _apply_observation_boost(
    hits: list[dict[str, Any]],
    *,
    boost_paths: set[str],
    boost_amount: float,
) -> None:
    if not hits or not boost_paths or boost_amount <= 0:
        return
    for hit in hits:
        blob = _path_text(hit)
        for path in boost_paths:
            norm = str(path or "").strip().replace("\\", "/")
            if not norm:
                continue
            if norm in blob or blob in norm:
                prev = float(hit.get("unified_score") or hit.get("score") or 0.0)
                hit["unified_score"] = round(prev + boost_amount, 6)
                hit["score"] = hit["unified_score"]
                hit["observation_boost"] = True
                breakdown = dict(hit.get("score_breakdown") or {})
                breakdown["observation_boost"] = boost_amount
                hit["score_breakdown"] = breakdown
                break


def unified_hybrid_search(
    query: str,
    *,
    butler_memory: Any,
    project_memory: Any | None = None,
    project_name: str = "",
    project_workspace: Path | None = None,
    butler_home: Path | None = None,
    limit: int = 8,
) -> dict[str, Any]:
    q = str(query or "").strip()
    if not q:
        return {"ok": False, "error": "query is required"}


    if not unified_recall_enabled():
        return {
            "ok": False,
            "error": "BUTLER_MEMORY_UNIFIED_RECALL=0; hybrid unified recall unavailable",
        }

    lim = max(1, min(20, int(limit or 8)))
    per_source = max(lim, lim * 2)
    weights = unified_scope_weights()
    batches: list[tuple[str, list[dict[str, Any]]]] = []
    source_counts: dict[str, int] = {}

    semantic = getattr(butler_memory, "semantic", None)
    proj_filter = (project_name or "").strip() or None


    exp_rows = filter_non_conversation_experience(
        hybrid_experience_search(
            semantic,
            butler_memory.experience.search,
            q,
            project=proj_filter,
            limit=per_source,
            experience_store=butler_memory.experience,
        )
    )
    exp_norm = _normalize_batch(exp_rows, scope="experience", weight=weights["experience"])
    batches.append(("experience", exp_norm))
    source_counts["experience"] = len(exp_norm)

    proj_hits: list[dict[str, Any]] = []
    if project_memory is not None:

        display = resolve_project_display_name(project_memory) or project_name
        raw_hits, _mode = prefetch_project_memory_hits(
            project_memory,
            q,
            project_name=display,
            semantic=semantic,
            limit=per_source,
            semantic_enabled=semantic_memory_enabled(),
        )
        proj_hits = [
            {
                "content": h.get("content", ""),
                "section": h.get("section", ""),
                "score": h.get("score"),
                "source_id": h.get("source_id"),
                "source": "project",
            }
            for h in raw_hits
            if h.get("content")
        ]
    proj_norm = _normalize_batch(proj_hits, scope="project", weight=weights["project"])
    batches.append(("project", proj_norm))
    source_counts["project"] = len(proj_norm)


    home = Path(butler_home or get_butler_home()).expanduser().resolve()
    coding_payload = search_coding_experiences(
        q,
        limit=per_source,
        project_id=project_name,
        project_workspace=project_workspace,
        butler_home=home,
    )
    coding_rows = coding_payload.get("results") or [] if coding_payload.get("ok") else []
    coding_norm = _normalize_batch(coding_rows, scope="coding", weight=weights["coding"])
    batches.append(("coding", coding_norm))
    source_counts["coding"] = len(coding_norm)

    merged = merge_retrieval_hits(batches, limit=lim)
    for hit in merged:
        if "unified_score" not in hit:
            scope = str(hit.get("recall_scope") or "experience")
            weight = weights.get(scope, 0.33)
            hit["unified_score"] = round(float(hit.get("score") or 0.0) * weight, 6)
            hit["score"] = hit["unified_score"]

    boost_paths: set[str] = set()
    if observation_recall_enabled() and project_workspace is not None:

        obs = search_observation_recall(q, project_workspace=project_workspace, limit=10)
        if obs.get("ok"):
            boost_paths = {
                str(row.get("path") or "").strip()
                for row in (obs.get("results") or [])
                if str(row.get("path") or "").strip()
            }
    _apply_observation_boost(
        merged,
        boost_paths=boost_paths,
        boost_amount=observation_recall_boost(),
    )
    merged.sort(
        key=lambda h: float(h.get("unified_score") or h.get("score") or 0.0),
        reverse=True,
    )
    results = merged[:lim]


    record_scope_retrieval_safe(
        {
            "mode": "hybrid-unified",
            "fallbacks": 0,
            "candidates": len(results),
            "query": q,
            "scope": "hybrid",
        },
    )

    return {
        "ok": True,
        "scope": "hybrid",
        "query": q,
        "results": results,
        "source_counts": source_counts,
        "weights": weights,
        "observation_paths_used": sorted(boost_paths)[:5] if boost_paths else [],
    }


def unified_hybrid_search_json(**kwargs: Any) -> str:
    return json.dumps(unified_hybrid_search(**kwargs), ensure_ascii=False)


__all__ = ["unified_hybrid_search", "unified_hybrid_search_json"]

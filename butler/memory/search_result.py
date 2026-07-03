"""Normalize retrieval hits for CLI verbose output and structured tool JSON."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from butler.memory.semantic_config import hybrid_fts_weight, hybrid_vector_weight
from butler.memory.semantic_index import SOURCE_EXPERIENCE, SOURCE_PROJECT

_MD_SOURCE_ID_RE = re.compile(r"^[^:]+:md:(.+?)#h")


def chunk_id_for_hit(hit: dict[str, Any]) -> str:
    sid = hit.get("source_id")
    if sid is None:
        sid = hit.get("id")
    src = str(hit.get("source") or SOURCE_EXPERIENCE).strip() or SOURCE_EXPERIENCE
    if sid is not None and str(sid).strip():
        return f"{src}:{sid}"
    content = str(hit.get("content") or "").strip()
    return f"content:{hash(content) & 0xFFFFFFFF:08x}"


def source_path_for_hit(hit: dict[str, Any], *, project_workspace: Path | None = None) -> str:
    src = str(hit.get("source") or "").strip()
    if src in (SOURCE_PROJECT, "project", "project_memory"):
        sid = str(hit.get("source_id") or "")
        m = _MD_SOURCE_ID_RE.match(sid)
        if m:
            rel = m.group(1)
            if project_workspace is not None:
                return str((project_workspace / rel).resolve())
            proj = str(hit.get("project") or "").strip()
            if proj:
                return f"projects/{proj}/{rel}"
            return rel
        meta_path = ""
        from butler.memory.search_result_ops import parse_chunk_metadata_safe

        meta = parse_chunk_metadata_safe(str(hit.get("content") or ""))
        meta_path = str(meta.get("source_path") or "")
        if meta_path:
            if project_workspace is not None:
                return str((project_workspace / meta_path).resolve())
            proj = str(hit.get("project") or "").strip()
            if proj:
                return f"projects/{proj}/{meta_path}"
            return meta_path
        proj = str(hit.get("project") or "").strip()
        if project_workspace is not None:
            return str(project_workspace / "MEMORY.md")
        if proj:
            return f"projects/{proj}/.butler/memory/MEMORY.md"
        return "MEMORY.md"
    if src == "owner_profile":
        return "owner_profile.json"
    proj = str(hit.get("project") or "").strip()
    if proj:
        return f"experience.db (project={proj})"
    return "experience.db"


def score_breakdown_for_hit(hit: dict[str, Any]) -> dict[str, Any]:
    retrieval = str(hit.get("retrieval") or hit.get("mode") or "").strip()
    breakdown: dict[str, Any] = {
        "final_score": hit.get("score"),
        "retrieval": retrieval or None,
        "hybrid_vector_weight": round(hybrid_vector_weight(), 4),
        "hybrid_fts_weight": round(hybrid_fts_weight(), 4),
    }
    if "access_count" in hit:
        breakdown["access_count"] = hit.get("access_count")
    if hit.get("heading_boost") is not None:
        breakdown["heading_boost"] = hit.get("heading_boost")
    if hit.get("base_score") is not None:
        breakdown["base_score"] = hit.get("base_score")
    if hit.get("rank_score") is not None:
        breakdown["rank_score"] = hit.get("rank_score")
    from butler.memory.search_result_ops import parse_chunk_metadata_safe

    meta = parse_chunk_metadata_safe(str(hit.get("content") or ""))
    if meta.get("heading_path"):
        breakdown["heading_path"] = meta["heading_path"]
    if meta.get("parent_source_id"):
        breakdown["parent_source_id"] = meta["parent_source_id"]
    return breakdown


def enrich_search_hit(
    hit: dict[str, Any],
    *,
    project_workspace: Path | None = None,
) -> dict[str, Any]:
    item = dict(hit)
    item["chunk_id"] = chunk_id_for_hit(hit)
    item["source_path"] = source_path_for_hit(hit, project_workspace=project_workspace)
    item["score_breakdown"] = score_breakdown_for_hit(hit)
    from butler.memory.search_result_ops import parse_chunk_metadata_safe

    meta = parse_chunk_metadata_safe(str(hit.get("content") or ""))
    if meta.get("heading_path"):
        item["heading_path"] = meta["heading_path"]
    if meta.get("parent_source_id"):
        item["parent_source_id"] = meta["parent_source_id"]
    return item


__all__ = [
    "chunk_id_for_hit",
    "enrich_search_hit",
    "score_breakdown_for_hit",
    "source_path_for_hit",
]

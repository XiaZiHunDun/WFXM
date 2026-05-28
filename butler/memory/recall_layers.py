"""Progressive disclosure recall: index → timeline → fetch (claude-mem subset)."""

from __future__ import annotations

import json
import re
from typing import Any

from butler.env_parse import env_truthy
from butler.memory.search_result import chunk_id_for_hit, enrich_search_hit, source_path_for_hit
import logging

logger = logging.getLogger(__name__)

_LAYER_ENV = "BUTLER_MEMORY_RECALL_LAYERS"


def recall_layers_enabled() -> bool:
    return env_truthy(_LAYER_ENV, default=True)


def _parse_experience_id(chunk_id: str) -> int | None:
    s = str(chunk_id or "").strip()
    m = re.match(r"^(?:experience:)?(\d+)$", s, re.I)
    if m:
        return int(m.group(1))
    m = re.search(r":(\d+)$", s)
    if m:
        return int(m.group(1))
    try:
        return int(s)
    except ValueError:
        return None


def _est_tokens(text: str) -> int:
    return max(1, len(text or "") // 4)


def _title_from_hit(hit: dict[str, Any]) -> str:
    cat = str(hit.get("category") or "").strip()
    content = str(hit.get("content") or "").strip()
    first = content.split("\n", 1)[0].strip()[:120]
    if cat and first:
        return f"[{cat}] {first}"
    return first or cat or "memory"


def _search_hits(svc: Any, query: str, *, limit: int, project: str | None) -> list[dict[str, Any]]:
    from butler.session_lifecycle import filter_non_conversation_experience

    bm = svc._butler_global
    if bm is None:
        return []
    semantic = getattr(bm, "semantic", None)
    q = str(query or "").strip()
    if not q:
        recent = bm.experience.get_recent(limit=limit * 2)
        return filter_non_conversation_experience(recent)[:limit]

    from butler.memory.semantic_index import hybrid_experience_search

    rows = hybrid_experience_search(
        semantic,
        bm.experience.search,
        q,
        project=project,
        limit=limit,
        experience_store=bm.experience,
    )
    return filter_non_conversation_experience(rows)


def recall_index(
    svc: Any,
    args: dict[str, Any],
) -> str:
    query = str(args.get("query") or "").strip()
    limit = max(1, min(30, int(args.get("limit") or 20)))
    project = str(args.get("project") or "").strip() or None
    hits = _search_hits(svc, query, limit=limit, project=project)
    index: list[dict[str, Any]] = []
    for h in hits:
        enriched = enrich_search_hit(h, project_workspace=getattr(svc, "_project_root", None))
        cid = chunk_id_for_hit(enriched)
        content = str(enriched.get("content") or "")
        index.append(
            {
                "chunk_id": cid,
                "title": _title_from_hit(enriched),
                "category": enriched.get("category"),
                "project": enriched.get("project"),
                "score": enriched.get("score"),
                "est_tokens": _est_tokens(content),
                "source_path": source_path_for_hit(
                    enriched,
                    project_workspace=getattr(svc, "_project_root", None),
                ),
            }
        )
    return json.dumps(
        {
            "ok": True,
            "mode": "index",
            "query": query,
            "count": len(index),
            "items": index,
            "hint": "用 mode=fetch 且 ids=[chunk_id,...] 拉全文",
        },
        ensure_ascii=False,
    )


def recall_fetch(
    svc: Any,
    args: dict[str, Any],
) -> str:
    ids_raw = args.get("ids") or args.get("chunk_ids") or []
    if isinstance(ids_raw, str):
        ids_raw = [x.strip() for x in ids_raw.split(",") if x.strip()]
    if not isinstance(ids_raw, list):
        return json.dumps({"ok": False, "error": "ids must be a list"})
    bm = svc._butler_global
    if bm is None:
        return json.dumps({"ok": False, "error": "ButlerMemory not initialized"})

    row_ids = []
    for cid in ids_raw:
        rid = _parse_experience_id(str(cid))
        if rid is not None:
            row_ids.append(rid)
    if not row_ids:
        return json.dumps({"ok": False, "error": "no valid experience ids"})

    rows = bm.experience.fetch_by_ids(row_ids)
    try:
        bm.experience.record_access(row_ids)
    except Exception as exc:
        logger.debug("recall fetch skipped: %s", exc)
    items = []
    for row in rows:
        enriched = enrich_search_hit(row, project_workspace=getattr(svc, "_project_root", None))
        items.append(
            {
                "chunk_id": chunk_id_for_hit(enriched),
                "content": enriched.get("content"),
                "category": enriched.get("category"),
                "project": enriched.get("project"),
                "score_breakdown": enriched.get("score_breakdown"),
                "source_path": source_path_for_hit(
                    enriched,
                    project_workspace=getattr(svc, "_project_root", None),
                ),
            }
        )
    return json.dumps({"ok": True, "mode": "fetch", "items": items}, ensure_ascii=False)


def recall_timeline(
    svc: Any,
    args: dict[str, Any],
) -> str:
    anchor = str(args.get("anchor_id") or args.get("chunk_id") or "").strip()
    depth = max(1, min(20, int(args.get("depth") or 5)))
    rid = _parse_experience_id(anchor)
    bm = svc._butler_global
    if bm is None or rid is None:
        return json.dumps({"ok": False, "error": "anchor_id required (e.g. experience:42)"})

    rows = bm.experience.timeline_around(rid, before=depth, after=depth)
    from butler.session_lifecycle import filter_non_conversation_experience

    rows = filter_non_conversation_experience(rows)
    items = []
    for row in rows:
        enriched = enrich_search_hit(row, project_workspace=getattr(svc, "_project_root", None))
        items.append(
            {
                "chunk_id": chunk_id_for_hit(enriched),
                "title": _title_from_hit(enriched),
                "created_at": row.get("created_at"),
                "category": row.get("category"),
                "preview": str(row.get("content") or "")[:200],
                "is_anchor": int(row.get("id") or 0) == rid,
            }
        )
    return json.dumps(
        {"ok": True, "mode": "timeline", "anchor_id": anchor, "items": items},
        ensure_ascii=False,
    )


def dispatch_recall_mode(svc: Any, args: dict[str, Any], mode: str) -> str:
    if not recall_layers_enabled():
        return json.dumps({"ok": False, "error": "recall layers disabled"})
    m = (mode or "full").strip().lower()
    if m == "index":
        return recall_index(svc, args)
    if m == "fetch":
        return recall_fetch(svc, args)
    if m == "timeline":
        return recall_timeline(svc, args)
    return json.dumps({"ok": False, "error": f"unknown recall mode: {mode}"})

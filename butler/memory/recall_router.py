"""Unified recall dispatch (L5) — single entry for butler_recall scopes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol

from butler.config import get_butler_home
from butler.execution_context import get_current_session_key
from butler.memory.coding_recall import search_coding_experiences
from butler.memory.facade_ops import (
    discover_project_root,
    emit_recall_metric,
    record_recall_telemetry,
    refresh_project_facts,
    resolve_active_project_name,
)
from butler.memory.observation_recall import search_observation_recall
from butler.memory.project_memory import ProjectMemory
from butler.memory.query_decompose import decompose_query, subquery_enabled
from butler.memory.semantic_config import semantic_memory_enabled
from butler.memory.semantic_index import SemanticMemoryIndex, hybrid_experience_search
from butler.memory.semantic_project import (
    prefetch_project_memory_hits,
    resolve_project_display_name,
)
from butler.memory.transcript_recall import search_transcript_recall
from butler.memory.unified_recall import unified_hybrid_search
from butler.session.lifecycle import filter_non_conversation_experience


def memory_state_for_scope(scope: str) -> str:
    """Map recall scope to L5 three-state model (session | ssot | derived)."""
    s = str(scope or "").strip().lower()
    if s == "transcript":
        return "session"
    if s == "observation":
        return "derived"
    return "ssot"


def _extract_hit_texts(hits: list[Any]) -> list[str]:
    out: list[str] = []
    for h in hits:
        if isinstance(h, dict):
            text = h.get("content") or h.get("text") or h.get("summary")
            if text:
                out.append(str(text))
        elif isinstance(h, str) and h.strip():
            out.append(h.strip())
    return out


def _tag_results(results: list[dict[str, Any]], scope: str) -> list[dict[str, Any]]:
    state = memory_state_for_scope(scope)
    tagged: list[dict[str, Any]] = []
    for row in results:
        item = dict(row)
        item.setdefault("memory_state", state)
        item.setdefault("recall_scope", scope)
        tagged.append(item)
    return tagged


class RecallFacade(Protocol):
    _butler_global: Any
    _project_memory: Any
    _project_root: Path | None


def dispatch_recall(facade: RecallFacade, args: dict[str, Any]) -> str:
    """Route butler_recall by scope (experience default merges coding hits)."""
    if facade._butler_global is None:
        return json.dumps({"ok": False, "error": "ButlerMemory not initialized"})

    scope = str(args.get("scope", "experience") or "experience")
    if scope == "profile":
        text = facade._butler_global.profile.read()
        return json.dumps({"ok": True, "profile": text, "memory_state": "ssot"})

    if scope == "coding":
        return _recall_coding(facade, args)
    if scope == "transcript":
        return _recall_transcript(args)
    if scope == "observation":
        return _recall_observation(facade, args)
    if scope == "hybrid":
        return _recall_hybrid(facade, args)
    if scope == "project":
        return _recall_project(facade, args)
    return _recall_experience(facade, args)


def _recall_coding(facade: RecallFacade, args: dict[str, Any]) -> str:
    query = str(args.get("query", "") or "").strip()
    limit = max(1, int(args.get("limit", 8) or 8))
    proj_name = resolve_active_project_name() or str(args.get("project") or "").strip()
    ws = getattr(facade._project_memory, "project_dir", None) if facade._project_memory else None
    if ws is None and facade._project_root:
        ws = facade._project_root
    payload = search_coding_experiences(
        query,
        limit=limit,
        project_id=proj_name,
        project_workspace=Path(ws) if ws else None,
        butler_home=get_butler_home(),
    )
    if payload.get("ok") and query:
        record_recall_telemetry(
            {
                "mode": "coding-keyword",
                "fallbacks": 0,
                "candidates": len(payload.get("results") or []),
                "query": query,
                "scope": "coding",
            }
        )
    if payload.get("ok") and isinstance(payload.get("results"), list):
        payload = dict(payload)
        payload["results"] = _tag_results(payload["results"], "coding")
        payload["memory_state"] = "ssot"
    emit_recall_metric(
        "coding",
        query,
        len(payload.get("results") or []),
        hit_texts=_extract_hit_texts(payload.get("results") or []),
    )
    return json.dumps(payload, ensure_ascii=False)


def _recall_transcript(args: dict[str, Any]) -> str:
    query = str(args.get("query", "") or "").strip()
    limit = max(1, int(args.get("limit", 8) or 8))
    offset = max(0, int(args.get("offset") or 0))
    payload = search_transcript_recall(
        query,
        session_key=get_current_session_key() or "",
        limit=limit,
        offset=offset,
    )
    if payload.get("ok") and isinstance(payload.get("results"), list):
        payload = dict(payload)
        payload["results"] = _tag_results(payload["results"], "transcript")
        payload["memory_state"] = "session"
    emit_recall_metric(
        "transcript",
        query,
        int(payload.get("count") or len(payload.get("results") or [])),
        hit_texts=_extract_hit_texts(payload.get("results") or []),
    )
    return json.dumps(payload, ensure_ascii=False)


def _recall_observation(facade: RecallFacade, args: dict[str, Any]) -> str:
    query = str(args.get("query", "") or "").strip()
    limit = max(1, int(args.get("limit", 8) or 8))
    ws = getattr(facade._project_memory, "project_dir", None) if facade._project_memory else None
    if ws is None and facade._project_root:
        ws = facade._project_root
    payload = search_observation_recall(
        query,
        project_workspace=Path(ws) if ws else None,
        limit=limit,
    )
    if payload.get("ok") and isinstance(payload.get("results"), list):
        payload = dict(payload)
        payload["results"] = _tag_results(payload["results"], "observation")
        payload["memory_state"] = "derived"
    emit_recall_metric(
        "observation",
        query,
        int(payload.get("count") or len(payload.get("results") or [])),
        hit_texts=_extract_hit_texts(payload.get("results") or []),
    )
    return json.dumps(payload, ensure_ascii=False)


def _recall_hybrid(facade: RecallFacade, args: dict[str, Any]) -> str:
    query = str(args.get("query", "") or "").strip()
    limit = max(1, int(args.get("limit", 8) or 8))
    proj_name = resolve_active_project_name() or str(args.get("project") or "").strip()
    pm = facade._project_memory
    ws = getattr(pm, "project_dir", None) if pm else None
    if ws is None and facade._project_root:
        ws = facade._project_root
    payload = unified_hybrid_search(
        query,
        butler_memory=facade._butler_global,
        project_memory=pm,
        project_name=proj_name,
        project_workspace=Path(ws) if ws else None,
        butler_home=get_butler_home(),
        limit=limit,
    )
    if payload.get("ok") and isinstance(payload.get("results"), list):
        payload = dict(payload)
        tagged: list[dict[str, Any]] = []
        for row in payload["results"]:
            item = dict(row)
            sc = str(item.get("recall_scope") or "experience")
            item.setdefault("memory_state", memory_state_for_scope(sc))
            tagged.append(item)
        payload["results"] = tagged
    emit_recall_metric(
        "hybrid",
        query,
        len(payload.get("results") or []),
        hit_texts=_extract_hit_texts(payload.get("results") or []),
    )
    return json.dumps(payload, ensure_ascii=False)


def _recall_project(facade: RecallFacade, args: dict[str, Any]) -> str:
    pm = facade._project_memory
    if pm is None:
        root = discover_project_root()
        if root:
            pm = ProjectMemory(root)
            refresh_project_facts(pm)
    if pm is None:
        return json.dumps({"ok": False, "error": "no active project"})
    query = str(args.get("query", "") or "").strip()
    limit = max(1, int(args.get("limit", 8) or 8))
    proj_name = resolve_active_project_name()
    facts_text = pm.facts_for_prefetch(max_chars=800)
    hits: list[dict[str, Any]] = []
    if query:
        sem = getattr(facade._butler_global, "semantic", None)
        if not isinstance(sem, SemanticMemoryIndex):
            sem = None
        sem_enabled = semantic_memory_enabled()
        display = resolve_project_display_name(pm) or proj_name
        raw_hits, mode = prefetch_project_memory_hits(
            pm,
            query,
            project_name=display,
            semantic=sem,
            limit=limit,
            semantic_enabled=sem_enabled,
        )
        sub_queries = decompose_query(query) if subquery_enabled() and query else [query]
        hits = [
            {
                "content": h.get("content", ""),
                "section": h.get("section", ""),
                "mode": mode,
                "score": h.get("score"),
                "source_id": h.get("source_id"),
                "memory_state": "ssot",
            }
            for h in raw_hits
            if h.get("content")
        ]
        tel: dict[str, Any] = {
            "mode": f"project-{mode}",
            "fallbacks": 1 if sem_enabled and mode in {"keyword", "none"} else 0,
            "candidates": len(hits),
            "query": query,
        }
        if len(sub_queries) > 1:
            tel["sub_queries"] = sub_queries
            tel["mode"] = f"project-{mode}-subquery"
        record_recall_telemetry(tel)
    emit_recall_metric(
        "project",
        query,
        len(hits),
        hit_texts=_extract_hit_texts(hits) + ([facts_text] if facts_text else []),
    )
    return json.dumps(
        {
            "ok": True,
            "scope": "project",
            "memory_state": "ssot",
            "facts": facts_text,
            "results": hits,
            "project": proj_name,
        }
    )


def _merge_coding_into_experience_rows(
    facade: RecallFacade,
    query: str,
    rows: list[dict[str, Any]],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    if not query.strip():
        return rows
    proj_name = resolve_active_project_name() or ""
    ws = getattr(facade._project_memory, "project_dir", None) if facade._project_memory else None
    if ws is None and facade._project_root:
        ws = facade._project_root
    coding_payload = search_coding_experiences(
        query,
        limit=max(2, limit // 2),
        project_id=proj_name,
        project_workspace=Path(ws) if ws else None,
        butler_home=get_butler_home(),
    )
    if not coding_payload.get("ok"):
        return rows
    coding_rows = _tag_results(coding_payload.get("results") or [], "coding")
    seen = {str(r.get("content") or "")[:80] for r in rows}
    merged = list(rows)
    for row in coding_rows:
        key = str(row.get("content") or "")[:80]
        if key and key not in seen:
            merged.append(row)
            seen.add(key)
    return merged[:limit]


def _recall_experience(facade: RecallFacade, args: dict[str, Any]) -> str:
    query = str(args.get("query", "") or "").strip()
    limit = max(1, int(args.get("limit", 8) or 8))
    project = str(args.get("project", "") or "").strip()
    semantic = getattr(facade._butler_global, "semantic", None)
    proj_filter: str | None = (project or "").strip() or None
    if proj_filter is None:
        proj_filter = resolve_active_project_name() or None

    if not query:
        recent = facade._butler_global.experience.get_recent(limit=limit * 4)
        rows = filter_non_conversation_experience(recent)[:limit]
    else:
        rows = filter_non_conversation_experience(
            hybrid_experience_search(
                semantic,
                facade._butler_global.experience.search,
                query,
                project=proj_filter,
                limit=limit,
                experience_store=facade._butler_global.experience,
            )
        )
        rows = _merge_coding_into_experience_rows(facade, query, rows, limit=limit)

    rows = _tag_results(rows, "experience")
    emit_recall_metric(
        "experience",
        query,
        len(rows),
        hit_texts=_extract_hit_texts(rows),
    )
    return json.dumps(
        {
            "ok": True,
            "results": rows,
            "semantic": semantic is not None,
            "memory_state": "ssot",
        }
    )


__all__ = ["dispatch_recall", "memory_state_for_scope"]

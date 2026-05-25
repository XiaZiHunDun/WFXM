"""CLI memory search with optional verbose diagnostics (RAG P0)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from butler.memory.butler_memory import ButlerMemory
from butler.memory.search_result import enrich_search_hit
from butler.memory.semantic_config import (
    hybrid_fts_weight,
    hybrid_vector_weight,
    semantic_memory_enabled,
)
from butler.memory.semantic_index import hybrid_experience_search
from butler.memory.semantic_project import prefetch_project_memory_hits, resolve_project_display_name

_CLI_SESSION_KEY = "cli-memory-search"


def _resolve_project_memory(project_name: str) -> tuple[Any | None, str, Path | None]:
    from butler.memory.project_memory import ProjectMemory
    from butler.project_manager import get_project_manager

    name = (project_name or "").strip()
    pmgr = get_project_manager()
    proj = pmgr.get_project(name) if name else pmgr.get_current()
    if proj is None:
        return None, name, None
    ws = Path(proj.workspace).expanduser().resolve()
    if not ws.is_dir():
        return None, str(proj.name or name), None
    pmem = ProjectMemory(ws)
    display = str(proj.name or resolve_project_display_name(pmem))
    return pmem, display, ws


def run_memory_search(
    butler_home: Path,
    query: str,
    *,
    scope: str = "experience",
    limit: int = 8,
    project: str = "",
    tenant: str = "default",
    verbose: bool = False,
    json_out: bool = False,
) -> dict[str, Any]:
    q = str(query or "").strip()
    if not q:
        return {"ok": False, "error": "query is required"}

    home = Path(butler_home).expanduser().resolve()
    bm = ButlerMemory(home, tenant_id=str(tenant or "default"))
    lim = max(1, min(20, int(limit or 8)))
    sc = (scope or "experience").strip().lower()

    payload: dict[str, Any] = {
        "ok": True,
        "query": q,
        "scope": sc,
        "limit": lim,
        "semantic_enabled": semantic_memory_enabled() and bm.semantic is not None,
        "hybrid_vector_weight": round(hybrid_vector_weight(), 4),
        "hybrid_fts_weight": round(hybrid_fts_weight(), 4),
        "mode": "",
        "fallbacks": 0,
        "candidates": 0,
        "results": [],
    }

    from butler.execution_context import use_execution_context
    from butler.memory.retrieval_telemetry import get_last_retrieval

    orch_stub = type(
        "_OrchStub",
        (),
        {"butler_memory": bm, "_project_memory": None, "project_manager": None},
    )()

    with use_execution_context(orch_stub, session_key=_CLI_SESSION_KEY):
        if sc == "project":
            pmem, proj_name, ws = _resolve_project_memory(project)
            if pmem is None or not proj_name:
                return {
                    "ok": False,
                    "error": "no project selected; pass --project <name>",
                }
            hits, mode = prefetch_project_memory_hits(
                pmem,
                q,
                project_name=proj_name,
                semantic=bm.semantic,
                limit=lim,
                semantic_enabled=payload["semantic_enabled"],
            )
            from butler.memory.retrieval_telemetry import record_last_retrieval

            record_last_retrieval(
                _CLI_SESSION_KEY,
                {
                    "mode": f"project-{mode}",
                    "fallbacks": 1
                    if payload["semantic_enabled"] and mode in {"keyword", "none"}
                    else 0,
                    "candidates": len(hits),
                    "query": q,
                },
            )
            enriched = [
                enrich_search_hit(h, project_workspace=ws) for h in hits[:lim]
            ]
            payload["project"] = proj_name
            payload["results"] = enriched
            payload["mode"] = f"project-{mode}"
            payload["candidates"] = len(enriched)

        elif sc == "profile":
            if bm.semantic is None:
                return {
                    "ok": False,
                    "error": "BUTLER_SEMANTIC_MEMORY=0; profile vector search unavailable",
                }
            hits = bm.semantic.search_owner_profile(q, limit=lim)
            from butler.memory.retrieval_telemetry import record_last_retrieval

            record_last_retrieval(
                _CLI_SESSION_KEY,
                {
                    "mode": "profile-vector",
                    "fallbacks": 0,
                    "candidates": len(hits),
                    "query": q,
                },
            )
            payload["results"] = [enrich_search_hit(h) for h in hits]
            payload["mode"] = "profile-vector"
            payload["candidates"] = len(payload["results"])

        else:
            proj_filter = (project or "").strip() or None
            rows = hybrid_experience_search(
                bm.semantic,
                bm.experience.search,
                q,
                project=proj_filter,
                limit=lim,
                experience_store=bm.experience,
            )
            payload["results"] = [enrich_search_hit(h) for h in rows]
            last = get_last_retrieval(_CLI_SESSION_KEY)
            payload["mode"] = str(last.get("mode") or "experience")
            payload["fallbacks"] = int(last.get("fallbacks") or 0)
            payload["candidates"] = int(last.get("candidates") or len(payload["results"]))
            if proj_filter:
                payload["project_filter"] = proj_filter

    if payload["fallbacks"] == 0 and not payload.get("mode"):
        payload["mode"] = "none"

    if json_out:
        return payload
    _print_human(payload, verbose=verbose)
    return payload


def _print_human(payload: dict[str, Any], *, verbose: bool) -> None:
    if not payload.get("ok"):
        print(payload.get("error", "search failed"))
        return

    print(f"query: {payload.get('query')}")
    print(f"scope: {payload.get('scope')}")
    if payload.get("project"):
        print(f"project: {payload.get('project')}")
    if payload.get("project_filter"):
        print(f"project_filter: {payload.get('project_filter')}")
    print(
        f"semantic: {'on' if payload.get('semantic_enabled') else 'off'} | "
        f"hybrid weights vector={payload.get('hybrid_vector_weight')} "
        f"fts={payload.get('hybrid_fts_weight')}"
    )
    if verbose or payload.get("mode"):
        print(
            f"mode: {payload.get('mode')} | fallbacks: {payload.get('fallbacks', 0)} | "
            f"candidates: {payload.get('candidates', 0)}"
        )

    results = payload.get("results") or []
    if not results:
        print("(no hits)")
        return

    for i, hit in enumerate(results, 1):
        content = str(hit.get("content") or "").strip().replace("\n", " ")
        if len(content) > 200:
            content = content[:197] + "..."
        score = hit.get("score")
        chunk = hit.get("chunk_id") or ""
        print(f"\n[{i}] score={score} {chunk}")
        if verbose:
            print(f"    source_path: {hit.get('source_path')}")
            print(f"    retrieval: {hit.get('retrieval')}")
            sb = hit.get("score_breakdown") or {}
            print(f"    score_breakdown: {json.dumps(sb, ensure_ascii=False)}")
        print(f"    {content}")


def format_search_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


__all__ = ["format_search_json", "run_memory_search"]

"""CLI memory search with optional verbose diagnostics (RAG P0)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from butler.memory.butler_memory import ButlerMemory
from butler.memory.recall_scopes import parse_recall_scopes
from butler.memory.search_result import enrich_search_hit
from butler.memory.semantic_config import (
    hybrid_fts_weight,
    hybrid_vector_weight,
    semantic_memory_enabled,
)
from butler.memory.semantic_index import hybrid_experience_search
from butler.memory.semantic_project import prefetch_project_memory_hits, resolve_project_display_name
from butler.memory.project_memory import ProjectMemory
from butler.project.manager import get_project_manager
from butler.execution_context import use_execution_context
from butler.memory.retrieval_telemetry import get_last_retrieval, record_last_retrieval
from butler.memory.coding_recall import search_coding_experiences
from butler.memory.transcript_recall import search_transcript_recall
from butler.memory.observation_recall import search_observation_recall
from butler.memory.unified_recall import unified_hybrid_search

_CLI_SESSION_KEY = "cli-memory-search"


def _resolve_project_memory(project_name: str) -> tuple[Any | None, str, Path | None]:

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


def _search_single_scope(
    bm: ButlerMemory,
    home: Path,
    q: str,
    *,
    scope: str,
    lim: int,
    project: str,
    semantic_enabled: bool,
) -> dict[str, Any]:
    sc = (scope or "experience").strip().lower()
    payload: dict[str, Any] = {
        "ok": True,
        "query": q,
        "scope": sc,
        "limit": lim,
        "semantic_enabled": semantic_enabled and bm.semantic is not None,
        "mode": "",
        "fallbacks": 0,
        "candidates": 0,
        "results": [],
    }


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
                    "scope": sc,
                }
            hits, mode = prefetch_project_memory_hits(
                pmem,
                q,
                project_name=proj_name,
                semantic=bm.semantic,
                limit=lim,
                semantic_enabled=payload["semantic_enabled"],
            )
            record_last_retrieval(
                _CLI_SESSION_KEY,
                {
                    "mode": f"project-{mode}",
                    "fallbacks": 1
                    if payload["semantic_enabled"] and mode in {"keyword", "none"}
                    else 0,
                    "candidates": len(hits),
                    "query": q,
                    "scope": "project",
                },
            )
            enriched = [enrich_search_hit(h, project_workspace=ws) for h in hits[:lim]]
            payload["project"] = proj_name
            payload["results"] = enriched
            payload["mode"] = f"project-{mode}"
            payload["candidates"] = len(enriched)

        elif sc == "coding":

            pmem, proj_name, ws = _resolve_project_memory(project)
            payload_coding = search_coding_experiences(
                q,
                limit=lim,
                project_id=proj_name or (project or "").strip(),
                project_workspace=ws,
                butler_home=home,
            )
            if not payload_coding.get("ok"):
                return cast(dict[str, Any], payload_coding)
            payload["results"] = payload_coding.get("results") or []
            payload["mode"] = "coding-keyword"
            payload["candidates"] = len(payload["results"])
            if proj_name:
                payload["project"] = proj_name
            record_last_retrieval(
                _CLI_SESSION_KEY,
                {
                    "mode": "coding-keyword",
                    "fallbacks": 0,
                    "candidates": payload["candidates"],
                    "query": q,
                    "scope": "coding",
                },
            )

        elif sc == "transcript":

            payload_transcript = search_transcript_recall(
                q,
                session_key="",
                limit=lim,
            )
            if not payload_transcript.get("ok"):
                return cast(dict[str, Any], payload_transcript)
            payload["results"] = payload_transcript.get("results") or []
            payload["mode"] = str(payload_transcript.get("mode") or "transcript")
            payload["candidates"] = len(payload["results"])

        elif sc == "profile":
            if bm.semantic is None:
                return {
                    "ok": False,
                    "error": "BUTLER_SEMANTIC_MEMORY=0; profile vector search unavailable",
                    "scope": sc,
                }
            hits = bm.semantic.search_owner_profile(q, limit=lim)
            record_last_retrieval(
                _CLI_SESSION_KEY,
                {
                    "mode": "profile-vector",
                    "fallbacks": 0,
                    "candidates": len(hits),
                    "query": q,
                    "scope": "profile",
                },
            )
            payload["results"] = [enrich_search_hit(h) for h in hits]
            payload["mode"] = "profile-vector"
            payload["candidates"] = len(payload["results"])

        elif sc == "observation":

            _pmem, proj_name, ws = _resolve_project_memory(project)
            payload_obs = search_observation_recall(q, project_workspace=ws, limit=lim)
            if not payload_obs.get("ok"):
                return cast(dict[str, Any], payload_obs)
            payload["results"] = payload_obs.get("results") or []
            payload["mode"] = "observation-keyword"
            payload["candidates"] = len(payload["results"])
            if proj_name:
                payload["project"] = proj_name

        elif sc == "hybrid":

            pmem, proj_name, ws = _resolve_project_memory(project)
            payload_hybrid = unified_hybrid_search(
                q,
                butler_memory=bm,
                project_memory=pmem,
                project_name=proj_name or (project or "").strip(),
                project_workspace=ws,
                butler_home=home,
                limit=lim,
            )
            if not payload_hybrid.get("ok"):
                return cast(dict[str, Any], payload_hybrid)
            payload["results"] = [
                enrich_search_hit(h, project_workspace=ws) for h in (payload_hybrid.get("results") or [])
            ]
            payload["mode"] = "hybrid-unified"
            payload["candidates"] = len(payload["results"])
            payload["source_counts"] = payload_hybrid.get("source_counts") or {}
            payload["weights"] = payload_hybrid.get("weights") or {}
            if proj_name:
                payload["project"] = proj_name

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

    return payload


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

    scopes, scope_err = parse_recall_scopes(scope)
    if scope_err:
        return {"ok": False, "error": scope_err}

    home = Path(butler_home).expanduser().resolve()
    bm = ButlerMemory(home, tenant_id=str(tenant or "default"))
    lim = max(1, min(20, int(limit or 8)))
    sc_raw = (scope or "experience").strip().lower()
    sem_enabled = semantic_memory_enabled() and bm.semantic is not None

    if len(scopes) == 1:
        payload = _search_single_scope(
            bm,
            home,
            q,
            scope=scopes[0],
            lim=lim,
            project=project,
            semantic_enabled=sem_enabled,
        )
        payload.setdefault("hybrid_vector_weight", round(hybrid_vector_weight(), 4))
        payload.setdefault("hybrid_fts_weight", round(hybrid_fts_weight(), 4))
        if json_out:
            return payload
        _print_human(payload, verbose=verbose)
        return payload

    by_scope: dict[str, Any] = {}
    total_candidates = 0
    any_ok = False
    for s in scopes:
        sub = _search_single_scope(
            bm,
            home,
            q,
            scope=s,
            lim=lim,
            project=project,
            semantic_enabled=sem_enabled,
        )
        by_scope[s] = sub
        if sub.get("ok"):
            any_ok = True
            total_candidates += int(sub.get("candidates") or len(sub.get("results") or []))

    multi_payload: dict[str, Any] = {
        "ok": any_ok,
        "query": q,
        "scope": sc_raw,
        "scopes": scopes,
        "limit": lim,
        "semantic_enabled": sem_enabled,
        "hybrid_vector_weight": round(hybrid_vector_weight(), 4),
        "hybrid_fts_weight": round(hybrid_fts_weight(), 4),
        "by_scope": by_scope,
        "candidates": total_candidates,
    }
    if not any_ok:
        errors = [
            f"{s}: {sub.get('error')}"
            for s, sub in by_scope.items()
            if sub.get("error")
        ]
        multi_payload["error"] = "; ".join(errors) if errors else "all scopes failed"

    if json_out:
        return multi_payload
    _print_human_multi(multi_payload, verbose=verbose)
    return multi_payload


def _print_hit_block(hit: dict[str, Any], index: int, *, verbose: bool) -> None:
    content = str(hit.get("content") or hit.get("preview") or hit.get("pattern") or "").strip()
    content = content.replace("\n", " ")
    if len(content) > 200:
        content = content[:197] + "..."
    score = hit.get("score")
    chunk = hit.get("chunk_id") or hit.get("session_key") or hit.get("id") or ""
    print(f"\n[{index}] score={score} {chunk}")
    if verbose:
        if hit.get("source_path"):
            print(f"    source_path: {hit.get('source_path')}")
        if hit.get("retrieval"):
            print(f"    retrieval: {hit.get('retrieval')}")
        sb = hit.get("score_breakdown") or {}
        if sb:
            print(f"    score_breakdown: {json.dumps(sb, ensure_ascii=False)}")
        if hit.get("line"):
            print(f"    line: {hit.get('line')}")
    print(f"    {content}")


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
        _print_hit_block(hit, i, verbose=verbose)


def _print_human_multi(payload: dict[str, Any], *, verbose: bool) -> None:
    if not payload.get("ok"):
        print(payload.get("error", "search failed"))
        return

    print(f"query: {payload.get('query')}")
    print(f"scopes: {', '.join(payload.get('scopes') or [])}")
    print(
        f"semantic: {'on' if payload.get('semantic_enabled') else 'off'} | "
        f"total candidates: {payload.get('candidates', 0)}"
    )
    by_scope = payload.get("by_scope") or {}
    for scope_name, sub in by_scope.items():
        print(f"\n--- scope={scope_name} ---")
        if not sub.get("ok"):
            print(f"  error: {sub.get('error', 'failed')}")
            continue
        print(
            f"  mode: {sub.get('mode')} | candidates: {sub.get('candidates', 0)}"
        )
        results = sub.get("results") or []
        if not results:
            print("  (no hits)")
            continue
        for i, hit in enumerate(results, 1):
            _print_hit_block(hit, i, verbose=verbose)


def format_search_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


__all__ = ["format_search_json", "run_memory_search"]

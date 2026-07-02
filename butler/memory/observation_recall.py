"""Observation store keyword recall (P3-H phase 3, opt-in)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def search_observation_recall(
    query: str,
    *,
    project_workspace: Path | None = None,
    limit: int = 8,
) -> dict[str, Any]:
    q = str(query or "").strip()
    if len(q) < 2:
        return {"ok": False, "error": "query is required (≥2 chars)"}

    from butler.memory.unified_recall_config import observation_recall_enabled

    if not observation_recall_enabled():
        return {
            "ok": False,
            "error": "BUTLER_MEMORY_OBSERVATION_RECALL=0; observation recall unavailable",
        }

    ws = project_workspace
    if ws is None:
        try:
            from butler.project.manager import get_project_manager

            proj = get_project_manager().get_current()
            if proj is not None and getattr(proj, "workspace", None):
                ws = Path(proj.workspace).expanduser().resolve()
        except Exception:
            ws = None

    if ws is None or not ws.is_dir():
        return {"ok": False, "error": "no project workspace for observation store"}

    from butler.memory.observation_store import ObservationStore, observations_db_path

    db_path = observations_db_path(ws)
    if not db_path.is_file():
        return {
            "ok": True,
            "scope": "observation",
            "query": q,
            "project_workspace": str(ws),
            "results": [],
            "hint": "observations.db missing (enable BUTLER_MEMORY_OBSERVER_QUEUE)",
        }

    store = ObservationStore(db_path)
    hits = store.search(q, limit=max(1, min(20, int(limit or 8))))
    try:
        from butler.execution_context import get_current_session_key
        from butler.memory.retrieval_telemetry import record_last_retrieval

        sk = get_current_session_key() or ""
        if sk:
            record_last_retrieval(
                sk,
                {
                    "mode": "observation-keyword",
                    "fallbacks": 0,
                    "candidates": len(hits),
                    "query": q,
                    "scope": "observation",
                },
            )
    except Exception:
        pass

    return {
        "ok": True,
        "scope": "observation",
        "query": q,
        "project_workspace": str(ws),
        "results": hits,
        "count": len(hits),
    }


def search_observation_recall_json(**kwargs: Any) -> str:
    return json.dumps(search_observation_recall(**kwargs), ensure_ascii=False)


__all__ = ["search_observation_recall", "search_observation_recall_json"]

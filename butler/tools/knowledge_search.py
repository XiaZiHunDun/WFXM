"""Project-scoped hybrid knowledge search (C8 light RAG — uses existing semantic index)."""

from __future__ import annotations

import json
from typing import Any


def tool_search_project_knowledge(
    query: str = "",
    limit: int = 8,
    **_: Any,
) -> str:
    """Search project MEMORY + semantic index (wrapper over butler_recall project scope)."""
    q = str(query or "").strip()
    lim = max(1, min(20, int(limit or 8)))
    from butler.tools.knowledge_search_ops import multi_scope_recall_safe

    routed = multi_scope_recall_safe(q, limit=lim)
    if routed is not None:
        return routed
    from butler.tools.memory_tools import tool_butler_recall

    raw = tool_butler_recall(scope="project", query=q, limit=lim)
    return _enrich_project_knowledge_json(raw)


def _enrich_project_knowledge_json(raw: str) -> str:
    """Add chunk_id / source_path / score_breakdown to project recall JSON (P0 structured)."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return raw
    if not isinstance(data, dict) or not data.get("ok"):
        return raw
    results = data.get("results")
    if not isinstance(results, list):
        return raw
    from butler.memory.search_result import enrich_search_hit

    ws = None
    proj = str(data.get("project") or "").strip()
    if proj:
        from butler.tools.knowledge_search_ops import resolve_project_workspace_for_enrich_safe

        ws = resolve_project_workspace_for_enrich_safe(proj)
    enriched = []
    for row in results:
        if isinstance(row, dict):
            enriched.append(enrich_search_hit(row, project_workspace=ws))
        else:
            enriched.append(row)
    data["results"] = enriched
    return json.dumps(data, ensure_ascii=False)


def register_knowledge_tools(register_fn) -> None:
    register_fn(
        name="search_project_knowledge",
        description=(
            "Hybrid search over current project MEMORY.md, facts, and semantic index. "
            "Prefer this for 'what did we decide about X in this project?' questions."
        ),
        schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "limit": {"type": "integer", "default": 8, "minimum": 1, "maximum": 20},
            },
            "required": ["query"],
        },
        handler=tool_search_project_knowledge,
        toolset="memory",
    )

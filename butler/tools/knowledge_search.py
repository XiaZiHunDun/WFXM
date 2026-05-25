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
    try:
        from butler.memory.corpus_router import corpus_routing_enabled, multi_scope_recall

        if corpus_routing_enabled() and q:
            return multi_scope_recall(q, limit=lim)
    except Exception:
        pass
    from butler.tools.memory_tools import tool_butler_recall

    return tool_butler_recall(scope="project", query=q, limit=lim)


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
        handler=lambda args: tool_search_project_knowledge(
            query=str((args or {}).get("query") or ""),
            limit=int((args or {}).get("limit") or 8),
        ),
        toolset="memory",
    )

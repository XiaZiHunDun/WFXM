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
    from butler.tools.memory_tools import tool_butler_recall

    return tool_butler_recall(
        scope="project",
        query=str(query or "").strip(),
        limit=max(1, min(20, int(limit or 8))),
    )


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

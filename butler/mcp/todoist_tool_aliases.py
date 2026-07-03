"""Resolve common LLM mis-names for Todoist MCP tools (EXT-2)."""

from __future__ import annotations

from typing import Any


def resolve_todoist_mcp_tool_name(name: str) -> str:
    key = str(name or "").strip()
    from butler.mcp.todoist_tool_aliases_ops import resolve_mcp_tool_alias_safe

    resolved = resolve_mcp_tool_alias_safe(key)
    if resolved != key:
        return resolved
    return key


def normalize_todoist_mcp_args(
    tool_name: str,
    args: dict[str, Any],
) -> dict[str, Any]:
    out = dict(args or {})
    resolved = resolve_todoist_mcp_tool_name(tool_name)
    if resolved == "mcp_todoist_lst_tasks":
        limit = out.get("limit")
        if limit is None:
            out["limit"] = 20
    return out

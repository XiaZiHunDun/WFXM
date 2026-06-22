"""Resolve common LLM mis-names for Todoist MCP tools (EXT-2)."""

from __future__ import annotations

from typing import Any


def resolve_todoist_mcp_tool_name(name: str) -> str:
    key = str(name or "").strip()
    try:
        from butler.mcp.extension_manifest import resolve_tool_alias

        resolved = resolve_tool_alias(key)
        if resolved != key:
            return resolved
    except Exception:
        pass
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

"""Todoist MCP tool alias resolution best-effort helpers (P0-A)."""

from __future__ import annotations

from butler.core.best_effort import safe_best_effort


def resolve_mcp_tool_alias_safe(name: str) -> str:
    key = str(name or "").strip()

    def _run() -> str:
        from butler.mcp.extension_manifest import resolve_tool_alias

        return str(resolve_tool_alias(key))

    result = safe_best_effort(
        _run,
        label="todoist_tool_aliases.resolve",
        default=key,
    )
    text = str(result or "").strip()
    return text or key

"""ToolsEngine manifest merge best-effort helpers (P0-A)."""

from __future__ import annotations

from typing import Any

from butler.core.best_effort import safe_best_effort


def filter_tools_manifest_safe(
    tools: list[dict],
) -> tuple[list[dict], dict[str, Any]]:
    def _run() -> tuple[list[dict], dict[str, Any]]:
        from butler.mcp.tools_manifest import filter_tools_by_mcp_ssot

        return filter_tools_by_mcp_ssot(list(tools))

    result = safe_best_effort(
        _run,
        label="tools_engine.manifest_merge",
        default=(list(tools), {}),
    )
    if isinstance(result, tuple) and len(result) == 2:
        working, diag = result
        if isinstance(working, list) and isinstance(diag, dict):
            return working, diag
    return list(tools), {}

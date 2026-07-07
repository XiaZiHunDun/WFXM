"""MCP SSOT tools manifest best-effort helpers (P0-A)."""

from __future__ import annotations

from pathlib import Path
from typing import cast

from butler.core.best_effort import safe_best_effort


def resolve_workspace_safe() -> Path | None:
    def _run() -> Path | None:
        from butler.registry.mcp_merge import resolve_workspace_for_session

        return cast(Path, resolve_workspace_for_session())

    result = safe_best_effort(
        _run,
        label="tools_manifest.resolve_workspace",
        default=None,
    )
    return result if isinstance(result, Path) else None


def effective_mcp_server_ids_safe(*, workspace: Path | None = None) -> set[str]:
    def _run() -> set[str]:
        from butler.registry.mcp_merge import effective_mcp_servers

        rows = effective_mcp_servers(workspace=workspace)
        return {str(r.server_id) for r in rows if r.server_id}

    result = safe_best_effort(
        _run,
        label="tools_manifest.effective_servers",
        default=set(),
    )
    return set(result) if isinstance(result, set) else set()

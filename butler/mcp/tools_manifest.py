"""Merge MCP SSOT / effective servers into ToolsEngine filtering (主线 J P2)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from butler.env_parse import env_truthy
from butler.mcp.naming import is_mcp_registered_name, safe_segment, tool_prefix

logger = logging.getLogger(__name__)


def tools_engine_ssot_enabled() -> bool:
    return env_truthy("BUTLER_TOOLS_ENGINE_SSOT", default=False)


def _resolve_workspace() -> Path | None:
    from butler.mcp.tools_manifest_ops import resolve_workspace_safe

    return resolve_workspace_safe()


def effective_mcp_server_ids(*, workspace: Path | None = None) -> set[str]:
    ws = workspace if workspace is not None else _resolve_workspace()
    from butler.mcp.tools_manifest_ops import effective_mcp_server_ids_safe

    return effective_mcp_server_ids_safe(workspace=ws)


def mcp_tool_matches_server(tool_name: str, server_id: str) -> bool:
    prefix = tool_prefix() + "_"
    if not str(tool_name or "").startswith(prefix):
        return False
    seg = safe_segment(server_id)
    return str(tool_name).startswith(f"{prefix}{seg}_")


def filter_tools_by_mcp_ssot(
    tools: list[dict],
    *,
    workspace: Path | None = None,
) -> tuple[list[dict], dict[str, Any]]:
    """Drop MCP tools whose server is not in effective mcp.yaml merge view."""
    diag: dict[str, Any] = {"tools_manifest_input": len(tools)}
    if not tools_engine_ssot_enabled():
        diag["tools_manifest_skipped"] = True
        return list(tools), diag

    server_ids = effective_mcp_server_ids(workspace=workspace)
    diag["tools_manifest_servers"] = sorted(server_ids)
    if not server_ids:
        kept: list[dict] = []
        dropped = 0
        for row in tools:
            name = str((row.get("function") or {}).get("name") or "")
            if is_mcp_registered_name(name):
                dropped += 1
                continue
            kept.append(row)
        diag["tools_manifest_dropped_mcp"] = dropped
        return kept, diag

    kept = []
    dropped = 0
    for row in tools:
        name = str((row.get("function") or {}).get("name") or "")
        if not is_mcp_registered_name(name):
            kept.append(row)
            continue
        if any(mcp_tool_matches_server(name, sid) for sid in server_ids):
            kept.append(row)
        else:
            dropped += 1
    diag["tools_manifest_dropped_mcp"] = dropped
    return kept, diag


__all__ = [
    "effective_mcp_server_ids",
    "filter_tools_by_mcp_ssot",
    "mcp_tool_matches_server",
    "tools_engine_ssot_enabled",
]

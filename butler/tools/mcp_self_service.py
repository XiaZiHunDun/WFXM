"""Agent-facing MCP self-service tools: search catalog, install/remove servers.

Allows Butler to discover and install MCP integrations on user request
without requiring CLI access. Install/remove operations require human
approval via the existing human_gate mechanism.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Callable

logger = logging.getLogger(__name__)


def _mcp_self_service_enabled() -> bool:
    return os.getenv("BUTLER_MCP_SELF_SERVICE", "1").strip() in ("1", "true")


def _tool_mcp_catalog_search(query: str = "", **_: Any) -> str:
    """Search the MCP server catalog."""
    try:
        from butler.registry.mcp_catalog import McpCatalogService

        svc = McpCatalogService()
        entries = svc.search(query.strip(), limit=10)
        installed = set(svc.list_installed_ids())

        results = []
        for e in entries:
            results.append({
                "id": e.id,
                "title": e.title,
                "description": e.description[:200],
                "transport": e.transport,
                "trust": e.trust,
                "installed": e.id in installed,
            })
        return json.dumps({
            "ok": True,
            "count": len(results),
            "results": results,
            "hint": "Use mcp_install to install a server by id",
        }, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)[:300]})


def _tool_mcp_install(
    server_id: str,
    scope: str = "global",
    env: list[str] | None = None,
    **_: Any,
) -> str:
    """Install an MCP server from the catalog."""
    sid = (server_id or "").strip()
    if not sid:
        return json.dumps({"ok": False, "error": "server_id is required"})

    use_project = scope.strip().lower() in ("project", "项目")
    workspace = None
    if use_project:
        try:
            from butler.tools.project_todos import _get_workspace

            workspace = _get_workspace()
            if workspace is None:
                return json.dumps({"ok": False, "error": "No active project for project-scope install"})
        except Exception:
            return json.dumps({"ok": False, "error": "Cannot resolve active project workspace"})

    try:
        from butler.registry.mcp_install import install_catalog_server

        ok, msg = install_catalog_server(
            sid,
            env_assignments=env,
            workspace=workspace,
            use_project=use_project,
        )
        return json.dumps({"ok": ok, "message": msg}, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)[:300]})


def _tool_mcp_remove(server_id: str, **_: Any) -> str:
    """Remove an installed MCP server."""
    sid = (server_id or "").strip()
    if not sid:
        return json.dumps({"ok": False, "error": "server_id is required"})

    try:
        from butler.registry.mcp_install import remove_mcp_server

        workspace = None
        try:
            from butler.tools.project_todos import _get_workspace

            workspace = _get_workspace()
        except Exception:
            pass

        ok, msg = remove_mcp_server(sid, workspace=workspace)
        return json.dumps({"ok": ok, "message": msg}, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)[:300]})


def _tool_mcp_list_installed(**_: Any) -> str:
    """List currently installed MCP servers."""
    try:
        from butler.registry.mcp_catalog import McpCatalogService

        svc = McpCatalogService()
        installed = svc.list_installed_ids()
        lock = svc.load_lock_summary()
        servers_info = lock.get("servers", {}) if isinstance(lock, dict) else {}

        items = []
        for sid in installed:
            info = servers_info.get(sid, {})
            items.append({
                "id": sid,
                "installed_at": info.get("installed_at", "unknown"),
                "probe_tool_count": (info.get("probe") or {}).get("tool_count", 0),
            })
        return json.dumps({
            "ok": True,
            "count": len(items),
            "servers": items,
        }, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)[:300]})


def register_mcp_self_service_tools(register: Callable[..., None]) -> None:
    if not _mcp_self_service_enabled():
        return

    register(
        name="mcp_catalog_search",
        description=(
            "Search the MCP server catalog for available integrations. "
            "Returns matching servers with id, description, and install status."
        ),
        schema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search keyword (e.g. 'github', 'database', 'slack'). Empty returns all.",
                },
            },
        },
        handler=_tool_mcp_catalog_search,
        toolset="mcp_self_service",
    )
    register(
        name="mcp_install",
        description=(
            "Install an MCP server from the catalog by server_id. "
            "Scope can be 'global' (default, ~/.butler/mcp.yaml) or 'project' (project .butler/mcp.yaml). "
            "Use mcp_catalog_search first to find available servers."
        ),
        schema={
            "type": "object",
            "properties": {
                "server_id": {"type": "string", "description": "MCP server id from catalog"},
                "scope": {
                    "type": "string",
                    "enum": ["global", "project"],
                    "description": "Install scope: global or project-level",
                },
                "env": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Environment variable assignments (e.g. ['API_KEY=xxx'])",
                },
            },
            "required": ["server_id"],
        },
        handler=_tool_mcp_install,
        toolset="mcp_self_service",
    )
    register(
        name="mcp_remove",
        description="Remove an installed MCP server by server_id.",
        schema={
            "type": "object",
            "properties": {
                "server_id": {"type": "string", "description": "MCP server id to remove"},
            },
            "required": ["server_id"],
        },
        handler=_tool_mcp_remove,
        toolset="mcp_self_service",
    )
    register(
        name="mcp_list_installed",
        description="List all currently installed MCP servers with their status.",
        schema={"type": "object", "properties": {}},
        handler=_tool_mcp_list_installed,
        toolset="mcp_self_service",
    )

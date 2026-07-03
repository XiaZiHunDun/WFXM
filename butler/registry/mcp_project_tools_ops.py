"""Project MCP tools wiring best-effort helpers (P0-A)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from butler.project import Project

logger = logging.getLogger(__name__)


def load_project_yaml_safe(path: Path) -> Project | None:
    try:
        return Project.from_yaml(path)
    except Exception as exc:
        logger.debug("project.yaml load %s: %s", path, exc)
        return None


def list_registered_tool_names_safe(server_id: str, block: dict[str, Any]) -> list[str]:
    names: list[str] = []
    try:
        from butler.mcp.config import _parse_server
        from butler.mcp.manager import McpConnectionManager

        cfg = _parse_server(server_id, block)
        if cfg is None:
            return names
        mgr = McpConnectionManager()
        refs = mgr.ensure_connected("registry-probe-list", workspace=None)
        for ref in refs:
            if ref.server_id == server_id:
                names.append(ref.registered_name)
        mgr.disconnect_all()
    except Exception as exc:
        logger.debug("list mcp tools %s: %s", server_id, exc)
    return sorted(names)

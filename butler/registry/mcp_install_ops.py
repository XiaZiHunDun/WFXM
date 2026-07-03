"""MCP catalog install best-effort helpers (P0-A)."""

from __future__ import annotations

import logging
import os
from typing import Any

from butler.registry.mcp_catalog import McpCatalogEntry

logger = logging.getLogger(__name__)


def run_pre_install_scan_gate_safe(
    entry: McpCatalogEntry,
    block: dict[str, Any],
) -> tuple[bool, str | None]:
    """Return ``(abort_install, message)`` when fail-closed scan blocks install."""
    try:
        from butler.registry.install_scan import (
            format_scan_message,
            install_pre_scan_fail_closed,
            pre_install_scan_mcp,
        )

        scan = pre_install_scan_mcp(entry, block)
        if not scan.ok_to_install and install_pre_scan_fail_closed():
            return True, format_scan_message(scan) + "\n安装已取消。"
    except Exception as exc:
        logger.debug("MCP pre-install scan skipped: %s", exc)
    return False, None


def probe_server_safe(server_id: str, block: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {"ok": False, "tool_count": 0, "error": ""}
    if os.getenv("BUTLER_MCP_ENABLED", "0").strip().lower() not in ("1", "true", "yes", "on"):
        result["error"] = "BUTLER_MCP_ENABLED=0 — skipped live probe"
        result["ok"] = True
        return result
    try:
        from butler.mcp.config import _parse_server, mcp_sdk_available

        if not mcp_sdk_available():
            result["error"] = "MCP SDK not installed (pip install butler-system[mcp])"
            result["ok"] = True
            return result
        cfg = _parse_server(server_id, block)
        if cfg is None:
            result["error"] = "Invalid server block"
            return result
        from butler.mcp.manager import McpConnectionManager

        mgr = McpConnectionManager()
        refs = mgr.ensure_connected("registry-probe", workspace=None)
        count = sum(1 for ref in refs if ref.server_id == server_id)
        mgr.disconnect_all()
        result["ok"] = True
        result["tool_count"] = count
    except Exception as exc:
        result["error"] = str(exc)[:200]
    return result


def reload_mcp_connections_safe() -> tuple[bool, str]:
    try:
        from butler.mcp.manager import McpConnectionManager

        McpConnectionManager().disconnect_all()
        return True, "MCP 连接已断开；下一 turn 将重读 mcp.yaml（含项目 .butler/mcp.yaml）。"
    except Exception as exc:
        return False, f"重载失败: {exc}"

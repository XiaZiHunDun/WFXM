"""MCP connection manager helpers (P0-A)."""

from __future__ import annotations

import logging
from typing import Any

from butler.core.best_effort import safe_best_effort

logger = logging.getLogger(__name__)


def close_mcp_handle_safe(handle: Any, *, run_cleanup: Any) -> None:
    def _run() -> None:
        run_cleanup()

    safe_best_effort(
        _run,
        label=f"mcp_manager.cleanup.{handle.config.server_id}",
        default=None,
    )
    handle.session = None
    handle.cleanup = None
    handle.status.connected = False


def filter_mcp_servers_by_profile_safe(
    configs: list[Any],
    *,
    session_key: str,
) -> list[Any]:
    def _run() -> list[Any]:
        from butler.mcp.profiles import (
            filter_servers_by_profile,
            get_session_profile,
            mcp_profiles_enabled,
        )

        if not mcp_profiles_enabled():
            return configs
        profile = get_session_profile(session_key=session_key)
        return filter_servers_by_profile(configs, profile)

    result = safe_best_effort(_run, label="mcp_manager.profile_filter", default=configs)
    return result if isinstance(result, list) else configs


def connect_handle_loud(
    handle: Any,
    *,
    server_id: str,
    run_connect: Any,
) -> bool:
    try:
        run_connect()
        return True
    except Exception as exc:
        msg = str(exc)[:300]
        handle.status.last_error = msg
        handle.status.degraded = True
        logger.error("MCP connect %s failed", server_id, exc_info=exc)
        return False


def call_tool_loud(
    handle: Any,
    *,
    server_id: str,
    tool_name: str,
    run_call: Any,
    on_error: Any,
) -> str:
    try:
        return run_call()
    except Exception as exc:
        handle.status.degraded = True
        handle.status.last_error = str(exc)[:300]
        logger.error(
            "MCP call_tool %s/%s failed",
            server_id,
            tool_name,
            exc_info=exc,
        )
        return on_error(str(exc))

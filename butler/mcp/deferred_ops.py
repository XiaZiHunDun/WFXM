"""MCP deferred tool discovery best-effort helpers (P0-A)."""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from butler.core.best_effort import safe_best_effort

logger = logging.getLogger(__name__)


def resolve_mcp_session_key_safe(session_key: str = "") -> str:
    key = str(session_key or "").strip()
    if key:
        return key

    def _run() -> str:
        from butler.execution_context import get_current_session_key

        return str(get_current_session_key() or "").strip() or "default"

    result = safe_best_effort(
        _run,
        label="mcp_deferred.session_key",
        default="default",
    )
    return str(result or "default")


def resolve_mcp_workspace_safe() -> Path | None:
    def _run() -> Path:
        from butler.execution_context import get_current_orchestrator, get_current_session_key

        orch = get_current_orchestrator()
        pm = getattr(orch, "project_manager", None) if orch else None
        if pm is None:
            raise ValueError("project manager unavailable")
        proj = pm.get_current(session_key=str(get_current_session_key() or ""))
        if proj is None:
            raise ValueError("no current project")
        return Path(proj.workspace)

    result = safe_best_effort(
        _run,
        label="mcp_deferred.workspace",
        default=None,
    )
    return result if isinstance(result, Path) else None


def warm_mcp_connection_safe(
    session_key: str,
    warm_fn: Callable[[str], Any],
) -> bool:
    try:
        warm_fn(session_key)
        return True
    except Exception as exc:
        logger.debug("MCP connect for experience promote failed: %s", exc)
        return False

"""Best-effort MCP registry hook helpers (P0-A)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from butler.core.best_effort import safe_best_effort


def resolve_workspace_safe() -> Path | None:
    def _run() -> Path | None:
        from butler.execution_context import get_current_orchestrator, get_current_session_key

        orch = get_current_orchestrator()
        if orch is None:
            return None
        pm = getattr(orch, "project_manager", None)
        if pm is None:
            return None
        proj = pm.get_current(session_key=str(get_current_session_key() or ""))
        if proj is None:
            return None
        return Path(proj.workspace)

    return safe_best_effort(_run, label="mcp.resolve_workspace", default=None)


def session_key_fallback(*, session_key: str = "") -> str:
    explicit = str(session_key or "").strip()
    if explicit:
        return explicit

    def _run() -> str:
        from butler.execution_context import get_current_session_key

        return str(get_current_session_key() or "").strip() or "default"

    return safe_best_effort(_run, label="mcp.session_key", default="default") or "default"


def resolve_session_key_for_connect(session_key: str = "") -> str:
    explicit = str(session_key or "").strip()
    if explicit:
        return explicit

    def _run() -> str:
        from butler.execution_context import get_current_session_key

        return str(get_current_session_key() or "").strip() or "default"

    result = safe_best_effort(_run, label="mcp.connect_session_key", default=None)
    if isinstance(result, str) and result.strip():
        return result.strip()
    return "default"


def maybe_deferred_mcp_definitions(session_key: str) -> list[dict[str, Any]] | None:
    def _run() -> list[dict[str, Any]] | None:
        from butler.core.harness_flags import mcp_deferred_tools_enabled
        from butler.mcp.deferred import get_deferred_mcp_definitions

        if not mcp_deferred_tools_enabled():
            return None
        return get_deferred_mcp_definitions(session_key)

    return safe_best_effort(_run, label="mcp.deferred_definitions", default=None)


def is_plan_mode_active(session_key: str) -> bool | None:
    def _run() -> bool:
        from butler.plan.mode import is_plan_mode

        return bool(is_plan_mode(session_key))

    return safe_best_effort(_run, label="mcp.plan_mode_check", default=None)


def run_mcp_with_gates_or_direct(
    *,
    server_id: str,
    tool_name: str,
    args: dict[str, Any],
    session_key: str,
    classification: str,
    run_fn: Callable[[], str],
) -> str:
    try:
        from butler.core.tool_orchestrator import run_mcp_with_gates

        return run_mcp_with_gates(
            server_id=server_id,
            tool_name=tool_name,
            args=args,
            session_key=session_key,
            classification=classification,
            run_fn=run_fn,
        )
    except Exception:
        return run_fn()


def mcp_warmup_safe(mgr: Any, session_key: str, workspace: Path | None) -> None:
    def _run() -> None:
        mgr.ensure_connected(session_key, workspace=workspace)

    safe_best_effort(_run, label="mcp.diagnostic_warmup", default=None)


def mcp_config_count_safe(workspace: Path | None) -> int | None:
    def _run() -> int:
        from butler.mcp.config import load_mcp_servers

        return len(load_mcp_servers(workspace=workspace))

    return safe_best_effort(_run, label="mcp.config_count", default=None)


def extension_verify_status_lines_safe() -> list[str]:
    def _run() -> list[str]:
        from butler.mcp.extension_verify import extension_verify_status_lines

        return extension_verify_status_lines()

    result = safe_best_effort(
        _run,
        label="mcp.extension_verify",
        default=None,
    )
    if isinstance(result, list):
        return result
    return []

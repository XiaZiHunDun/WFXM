"""Network search policy best-effort helpers (P0-A)."""

from __future__ import annotations

from typing import Any

from butler.core.best_effort import safe_best_effort


def is_github_mcp_intent_safe(query: str) -> bool:
    def _run() -> bool:
        from butler.mcp.github_grounding import (
            is_github_issue_list_intent,
            is_github_repo_list_intent,
        )

        return is_github_repo_list_intent(query) or is_github_issue_list_intent(query)

    result = safe_best_effort(
        _run,
        label="network_search.github_mcp_intent",
        default=False,
    )
    return bool(result)


def get_turn_bridge_safe() -> Any | None:
    def _run() -> Any:
        from butler.execution_context import get_current_turn_bridge

        return get_current_turn_bridge()

    return safe_best_effort(
        _run,
        label="network_search.turn_bridge",
        default=None,
    )


def epoch_user_query_safe() -> str:
    def _run() -> str:
        from butler.core.session_epoch import last_user_query_in_epoch
        from butler.execution_context import get_current_session_key

        sk = str(get_current_session_key() or "").strip()
        if sk:
            return str(last_user_query_in_epoch(sk) or "")
        return ""

    result = safe_best_effort(
        _run,
        label="network_search.epoch_query",
        default="",
    )
    return str(result or "")


def web_search_in_current_toolset_safe(*, fallback: bool) -> bool:
    def _run() -> bool:
        from butler.execution_context import get_current_orchestrator, get_current_session_key
        from butler.tools.project_tools import get_tool_definitions_for_project

        orch = get_current_orchestrator()
        if orch is None:
            return True
        pm = getattr(orch, "project_manager", None)
        if pm is None:
            return True
        proj = pm.get_current(session_key=str(get_current_session_key() or ""))
        for role in ("lead", "butler", "content", "dev", "review"):
            tools = get_tool_definitions_for_project(proj, role=role)
            names = {
                str((t.get("function") or {}).get("name") or "")
                for t in tools
                if isinstance(t, dict)
            }
            if "web_search" in names:
                return True
        return False

    result = safe_best_effort(
        _run,
        label="network_search.toolset_web_search",
        default=fallback,
    )
    return bool(result)

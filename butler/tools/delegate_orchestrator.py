"""Orchestrator resolution for delegate tools — isolated to avoid import cycles."""

from __future__ import annotations

from typing import Any

from butler.execution_context import get_current_orchestrator


def _orchestrator_for_tool(*, channel: str) -> Any:
    orch = get_current_orchestrator()
    if orch is not None:
        return orch

    from butler.orchestrator import ButlerOrchestrator

    return ButlerOrchestrator(user_id="owner", channel=channel)

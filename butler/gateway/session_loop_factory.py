"""Per-session AgentLoop factory for gateway (ENG-3)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from butler.core.agent_loop import AgentLoop
    from butler.gateway.message_handler import ButlerMessageHandler


def create_gateway_loop(handler: ButlerMessageHandler, session_key: str) -> AgentLoop:
    """Build an AgentLoop for a gateway session key."""
    from butler.gateway.handler_helpers import _inject_previous_session_summary
    from butler.plan.mode import is_plan_mode
    from butler.project.lead import gateway_loop_role
    from butler.tools.project_tools import get_tool_definitions_for_project
    from butler.tools.registry import dispatch_tool

    pm = handler._orchestrator.project_manager
    project = pm.get_current(session_key=session_key)
    proj_name = (
        str(getattr(project, "name", "") or "").strip()
        or pm.resolve_active_project_name(session_key=session_key)
    )
    loop_role = gateway_loop_role(proj_name, project=project)
    if is_plan_mode(session_key):
        loop_role = "plan"
    tools = get_tool_definitions_for_project(project, role=loop_role)
    loop = handler._orchestrator.create_agent_loop(
        role=loop_role,
        tools=tools,
        tool_dispatcher=dispatch_tool,
        session_key=session_key,
    )
    _inject_previous_session_summary(loop, project)
    from butler.core.session_hydration import hydrate_loop_on_create

    hydrate_loop_on_create(loop, session_key, project)
    return loop


__all__ = ["create_gateway_loop"]

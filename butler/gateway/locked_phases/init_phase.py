from __future__ import annotations

from typing import TYPE_CHECKING

from butler.core.best_effort import safe_best_effort
from butler.memory.memory_metrics import get_collector as _memory_metrics_collector
from butler.memory.metrics_persist import load_persisted_metrics
from butler.plan.mode import is_plan_mode
from butler.project.lead import gateway_loop_role

from .state import LockedTurnState

if TYPE_CHECKING:
    from butler.gateway.message_handler import ButlerMessageHandler


def _phase_init_loop_role(
    handler: "ButlerMessageHandler",
    state: LockedTurnState,
) -> None:
    pm = handler._orchestrator.project_manager
    proj_name = pm.resolve_active_project_name(session_key=state.session_key)
    proj = pm.get_current(session_key=state.session_key)
    state.loop_role = gateway_loop_role(proj_name, project=proj)
    if is_plan_mode(state.session_key):
        state.loop_role = "plan"
    state.health.update(
        {
            "session_key": state.session_key,
            "platform": state.platform,
            "platform_chat_id": state.external_id or "",
            "last_user_query": state.text.strip()[:500],
            "gateway_agent_role": state.loop_role,
        }
    )

    def _start_metrics_session() -> None:
        load_persisted_metrics()
        _memory_metrics_collector().start_session(state.session_key)

    safe_best_effort(_start_metrics_session, label="locked_phases.memory_metrics")

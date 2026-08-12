from __future__ import annotations

from typing import TYPE_CHECKING

from butler.core.best_effort import safe_best_effort
from butler.core.turn_token_budget import TurnBudgetState, resolve_turn_budget
from butler.core.agent_loop.loop_conversation import _init_turn_state
from butler.core.agent_loop.loop_helpers import _prepare_user_message
from butler.ops.eval_actions import apply_hard_feedback
from butler.ops.eval_feedback import get_feedback_context

from .state import TurnBodyState

if TYPE_CHECKING:
    from butler.core.agent_loop.loop import AgentLoop


def _phase_init(
    loop: "AgentLoop",
    user_message: str,
    steer_session: str,
    state: TurnBodyState,
) -> None:
    """Phase 1: state reset + turn budget resolution + user message prep."""
    _init_turn_state(loop, steer_session)

    state.original_config = loop.config
    state.steer_session = steer_session
    loop.config, turn_budget_tokens, cleaned_user = resolve_turn_budget(
        user_message, loop.config,
    )
    if turn_budget_tokens:
        state.budget_state = TurnBudgetState(int(turn_budget_tokens))
        loop.diagnostics["turn_token_budget"] = int(turn_budget_tokens)
    else:
        state.budget_state = None

    state.user_content, state.turn_tools = _prepare_user_message(
        loop, cleaned_user,
    )
    loop._turn_tools = state.turn_tools

    def _inject_feedback() -> None:
        feedback = get_feedback_context(lookback_hours=24.0)
        if feedback:
            loop._turn_ephemeral_system = (
                (loop._turn_ephemeral_system or "") + "\n" + feedback
            ).strip()
            loop.diagnostics["eval_feedback_injected"] = True

    safe_best_effort(_inject_feedback, label="agent_loop.eval_feedback")

    def _apply_hard_feedback() -> None:
        hard = apply_hard_feedback()
        if hard.get("applied"):
            loop.diagnostics["eval_hard_feedback"] = hard

    safe_best_effort(_apply_hard_feedback, label="agent_loop.hard_feedback")

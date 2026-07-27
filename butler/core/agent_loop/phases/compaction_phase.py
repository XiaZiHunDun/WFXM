from __future__ import annotations

from typing import TYPE_CHECKING

from butler.core.agent_loop.loop_helpers import _estimate_tokens
from butler.core.best_effort import safe_best_effort
from butler.core.compaction_steer_bridge import apply_compaction_turn_followup
from butler.core.compaction_task import run_compaction_turn, should_run_compaction_turn
from butler.core.loop_types import LoopTransitionReason

from .state import TurnBodyState, _audit_session_key

if TYPE_CHECKING:
    from butler.core.agent_loop.loop import AgentLoop


def _phase_maybe_compact_turn(
    loop: "AgentLoop",
    state: TurnBodyState,
) -> bool:
    """Run explicit compaction turn; return True if compacted (caller skips)."""
    if not should_run_compaction_turn(
        loop._messages,
        max_context_tokens=loop.config.max_context_tokens,
        estimate_tokens=lambda msgs: _estimate_tokens(loop, msgs),
        diagnostics=loop.diagnostics,
        iteration=state.iteration,
        max_output_tokens=getattr(loop.config, "max_output_tokens", None),
    ):
        return False
    did_compact, new_msgs = run_compaction_turn(
        loop._messages,
        compress=loop._compress_context,
        diagnostics=loop.diagnostics,
        iteration=state.iteration,
        session_key=_audit_session_key(fallback="default"),
    )
    if not did_compact:
        return False
    loop._messages[:] = new_msgs

    def _apply_followup() -> None:
        sk = _audit_session_key(fallback="default")
        loop._messages[:] = apply_compaction_turn_followup(
            loop._messages, sk, loop.diagnostics,
        )

    safe_best_effort(_apply_followup, label="agent_loop.compaction_followup")
    state.transition = LoopTransitionReason.COMPACTION_TURN
    return True
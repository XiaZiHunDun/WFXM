from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

from butler.core.best_effort import safe_best_effort
from butler.core.hook_context_adapter import adapt_hook_context_lines, apply_hook_context_to_diagnostics, to_hook_context_view
from butler.core.loop_types import LoopResult, LoopStatus, LoopTransitionReason
from butler.core.session_transcript import record_assistant_message
from butler.hooks.runner import run_stop_hooks
from butler.ops.runtime_metrics import inc, observe_ms

from .state import TurnBodyState, _store_reasoning_on_message

if TYPE_CHECKING:
    from butler.core.agent_loop.loop import AgentLoop

logger = logging.getLogger(__name__)


def _phase_finalize(
    loop: "AgentLoop",
    state: TurnBodyState,
    run_callbacks: Any,
    steer_session: str,
    start_time: float,
) -> None:
    """Phase 4: store final assistant message, record metrics, run stop hooks."""
    if state.status == LoopStatus.RUNNING:
        state.status = LoopStatus.TOOL_LIMIT
        state.transition = LoopTransitionReason.TOOL_LIMIT
    if state.final_text:
        _store_final_message(loop, state, steer_session)
    elapsed = time.time() - start_time
    loop.diagnostics["loop_transition_reason"] = state.transition.value
    _record_turn_metrics(loop, state, elapsed, steer_session)
    state.result = _build_loop_result(loop, state, run_callbacks, steer_session, elapsed)


def _store_final_message(
    loop: "AgentLoop",
    state: TurnBodyState,
    steer_session: str,
) -> None:
    """Append final assistant message + record transcript (best-effort)."""
    msg = {"role": "assistant", "content": state.final_text}
    _store_reasoning_on_message(msg, state.final_reasoning)
    loop._messages.append(msg)
    safe_best_effort(
        lambda: record_assistant_message(
            steer_session,
            state.final_text,
            tool_calls=loop._tool_calls_count,
        ),
        label="agent_loop.transcript_assistant",
    )


def _record_turn_metrics(
    loop: "AgentLoop",
    state: TurnBodyState,
    elapsed: float,
    steer_session: str,
) -> None:
    """Emit turn_duration + turn_finished metrics (best-effort)."""

    def _emit_metrics() -> None:
        labels = {
            "transition": str(state.transition.value)[:32],
            "status": str(state.status.value)[:16],
        }
        observe_ms(
            "turn_duration",
            elapsed * 1000.0,
            labels=labels,
            session_key=steer_session,
        )
        inc("turn_finished", labels=labels, session_key=steer_session)

    safe_best_effort(_emit_metrics, label="agent_loop.turn_metrics")


def _build_loop_result(
    loop: "AgentLoop",
    state: TurnBodyState,
    run_callbacks: Any,
    steer_session: str,
    elapsed: float,
) -> LoopResult:
    """Build the final LoopResult, run stop hooks, return."""
    result = LoopResult(
        status=state.status,
        transition_reason=state.transition.value,
        final_response=state.final_text,
        reasoning=state.final_reasoning,
        messages=list(loop._messages),
        iterations=state.iteration,
        total_tokens=loop._total_tokens,
        tool_calls_made=loop._tool_calls_count,
        elapsed_seconds=elapsed,
        diagnostics=dict(loop.diagnostics),
    )
    _maybe_run_stop_hooks(loop, state, result, steer_session)
    return result


def _maybe_run_stop_hooks(
    loop: "AgentLoop",
    state: TurnBodyState,
    result: LoopResult,
    steer_session: str,
) -> None:
    """Run post-run stop hooks if status is COMPLETED and no prior stop-hook context."""
    if loop.diagnostics.get("stop_hook_context"):
        logger.debug("Stop hook context already present, skipping post-run hooks")
        return
    if state.status != LoopStatus.COMPLETED:
        return

    def _run_hooks() -> None:
        stop_hooks = run_stop_hooks(
            status=state.status.value,
            last_assistant_message=state.final_text or "",
            session_key=steer_session,
            iterations=state.iteration,
            tool_calls=loop._tool_calls_count,
            elapsed_seconds=result.elapsed_seconds,
        )
        if stop_hooks.additional_context:
            adapted = adapt_hook_context_lines(
                stop_hooks.additional_context,
                source="stop_hook",
            )
            if adapted:
                loop.diagnostics["stop_hook_context"] = adapted
                view = to_hook_context_view(adapted, source="stop_hook_merged")
                apply_hook_context_to_diagnostics(view, loop.diagnostics)

    safe_best_effort(_run_hooks, label="agent_loop.stop_hooks")

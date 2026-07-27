from __future__ import annotations

from typing import TYPE_CHECKING, cast

from butler.core.best_effort import safe_best_effort
from butler.core.context_budget import record_usage_in_diagnostics, usage_billable_tokens
from butler.core.loop_budget_nudge import maybe_inject_loop_budget_nudges
from butler.core.loop_types import LoopStatus, LoopTransitionReason
from butler.core.agent_loop.loop_helpers import _call_llm_with_retry
from butler.execution_context import get_current_session_key
from butler.ops.cost_tracker import get_session_cost
from butler.transport.usage_normalize import normalize_usage

from .state import TurnBodyState

if TYPE_CHECKING:
    from butler.core.agent_loop.loop import AgentLoop
    from butler.transport.types import NormalizedResponse


def _phase_call_llm(
    loop: "AgentLoop",
    state: TurnBodyState,
) -> None:
    """Phase 2: LLM call with pre-callbacks, nudge, None handling, usage."""
    _emit_iteration_callbacks(loop, state)
    _inject_budget_nudge(loop, state)
    response = _call_llm_with_retry(loop)
    state.response = response
    if response is None:
        _mark_no_response(loop, state)


def _emit_iteration_callbacks(loop: "AgentLoop", state: TurnBodyState) -> None:
    """Emit stream-boundary (iteration > 1) and on_iteration callbacks."""
    if state.iteration > 1 and loop.callbacks.on_stream_boundary:
        loop.callbacks.on_stream_boundary()
    if loop.callbacks.on_iteration:
        loop.callbacks.on_iteration(state.iteration, state.status)


def _inject_budget_nudge(loop: "AgentLoop", state: TurnBodyState) -> None:
    """Inject loop budget nudge messages (best-effort)."""

    def _nudge() -> None:
        budget_tokens = (
            int(state.budget_state.budget_tokens)
            if state.budget_state is not None
            else None
        )
        maybe_inject_loop_budget_nudges(
            loop._messages,
            loop.diagnostics,
            iteration=state.iteration,
            max_iterations=loop.config.max_iterations,
            total_tokens=loop._total_tokens,
            budget_tokens=budget_tokens,
        )

    safe_best_effort(_nudge, label="agent_loop.budget_nudge")


def _mark_no_response(loop: "AgentLoop", state: TurnBodyState) -> None:
    """Set state.status/transition when LLM returned None (interrupt or error)."""
    if loop._interrupted:
        state.status = LoopStatus.INTERRUPTED
        state.transition = LoopTransitionReason.INTERRUPTED
        return
    state.status = LoopStatus.ERROR
    if loop.diagnostics.get("reactive_context_compact"):
        state.transition = LoopTransitionReason.REACTIVE_COMPACT_RETRY
    else:
        state.transition = LoopTransitionReason.LLM_ERROR


def _record_usage(
    loop: "AgentLoop",
    response: "NormalizedResponse",
    state: TurnBodyState,
) -> None:
    """Record token usage + diagnostics from a successful LLM response."""
    if not response.usage:
        return
    provider = str(getattr(loop.client, "provider_name", "") or "")
    loop.diagnostics["last_provider"] = provider
    loop.diagnostics["last_model"] = str(
        getattr(loop.client, "model_name", "") or ""
    )
    norm_usage = normalize_usage(response.usage, provider=provider)
    usage = norm_usage or response.usage
    billable = usage_billable_tokens(
        prompt_tokens=usage.prompt_tokens,
        completion_tokens=usage.completion_tokens,
        total_tokens=usage.total_tokens,
        cached_tokens=usage.cached_tokens,
    )
    loop._total_tokens += billable
    record_usage_in_diagnostics(
        loop.diagnostics,
        prompt_tokens=usage.prompt_tokens,
        completion_tokens=usage.completion_tokens,
        total_tokens=usage.total_tokens,
        cached_tokens=usage.cached_tokens,
    )

    def _record_cost() -> None:
        session_key = str(get_current_session_key() or "").strip()
        if not session_key:
            session_key = str(getattr(loop, "session_key", "") or "").strip()
        if session_key:
            model_name = str(
                getattr(loop.client, "model", "")
                or getattr(loop.client, "model_name", "")
                or ""
            )
            get_session_cost(session_key).record_llm_call(
                input_tokens=usage.prompt_tokens,
                output_tokens=usage.completion_tokens,
                model=model_name,
            )

    safe_best_effort(_record_cost, label="agent_loop.cost_record")
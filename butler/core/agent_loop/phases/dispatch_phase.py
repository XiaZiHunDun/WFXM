from __future__ import annotations

from typing import TYPE_CHECKING, Optional, cast

from butler.core.best_effort import safe_best_effort
from butler.core.loop_response import needs_truncation_continue, truncation_continue_message
from butler.core.loop_stuck import guardrail_stuck_message
from butler.core.loop_types import LoopStatus, LoopTransitionReason
from butler.core.output_grounding import apply_output_grounding
from butler.core.reasoning_trace import record_stuck_reflect
from butler.core.turn_token_budget import continuation_limits, get_budget_continuation_message
from butler.core.agent_loop.loop_helpers import _process_tool_calls
from butler.mcp.github_grounding import try_github_issue_list_direct_reply, try_github_repo_list_direct_reply
from butler.mcp.outbound_grounding_gate import try_correct_ungrounded_list_reply
from butler.mcp.todoist_grounding import try_todoist_project_list_direct_reply

from .state import TurnBodyState, _store_reasoning_on_message

if TYPE_CHECKING:
    from butler.core.agent_loop.loop import AgentLoop
    from butler.transport.types import NormalizedResponse


def _phase_dispatch_tools(
    loop: "AgentLoop",
    response: "NormalizedResponse",
    state: TurnBodyState,
    start_time: float,
    steer_session: str,
) -> bool:
    """Phase 3: dispatch LLM response. Returns True to continue, False to break."""
    if response.tool_calls:
        return _dispatch_tool_response(loop, response, state)
    _dispatch_text_response(loop, response, state, start_time, steer_session)
    return bool(state.status == LoopStatus.RUNNING)


def _dispatch_tool_response(
    loop: "AgentLoop",
    response: "NormalizedResponse",
    state: TurnBodyState,
) -> bool:
    """Tool path: process tool calls, then check early-termination signals."""
    batch_stats = _process_tool_calls(loop, response)

    def _try_github_repo_direct() -> bool:
        direct = try_github_repo_list_direct_reply(
            loop._messages,
            user_text=state.user_content,
        )
        if direct:
            state.final_text = direct
            state.status = LoopStatus.COMPLETED
            state.transition = LoopTransitionReason.SHOULD_CONTINUE_FALSE
            loop.diagnostics["github_repo_list_direct"] = True
            return True
        return False

    if safe_best_effort(_try_github_repo_direct, label="agent_loop.github_repo_direct"):
        return False

    def _try_github_issue_direct() -> bool:
        direct_issues = try_github_issue_list_direct_reply(
            loop._messages,
            user_text=state.user_content,
        )
        if direct_issues:
            state.final_text = direct_issues
            state.status = LoopStatus.COMPLETED
            state.transition = LoopTransitionReason.SHOULD_CONTINUE_FALSE
            loop.diagnostics["github_issue_list_direct"] = True
            return True
        return False

    if safe_best_effort(_try_github_issue_direct, label="agent_loop.github_issue_direct"):
        return False

    def _try_todoist_direct() -> bool:
        direct_todoist = try_todoist_project_list_direct_reply(
            loop._messages,
            user_text=state.user_content,
        )
        if direct_todoist:
            state.final_text = direct_todoist
            state.status = LoopStatus.COMPLETED
            state.transition = LoopTransitionReason.SHOULD_CONTINUE_FALSE
            loop.diagnostics["todoist_project_list_direct"] = True
            return True
        return False

    if safe_best_effort(_try_todoist_direct, label="agent_loop.todoist_direct"):
        return False

    waiting = getattr(batch_stats, "waiting_confirmation_message", None)
    if waiting:
        state.final_text = waiting
        state.status = LoopStatus.WAITING_CONFIRMATION
        state.transition = LoopTransitionReason.WAITING_CONFIRMATION
        loop.diagnostics["two_phase_confirm"] = True
        return False

    stuck = _get_stuck_message(loop)
    if stuck:

        def _reflect_stuck() -> None:
            record_stuck_reflect(loop, stuck)

        safe_best_effort(_reflect_stuck, label="agent_loop.stuck_reflect")
        state.final_text = stuck
        state.status = LoopStatus.STUCK
        state.transition = LoopTransitionReason.STUCK
        loop.diagnostics["loop_stuck"] = True
        return False

    clarification = getattr(batch_stats, "clarification_question", None)
    if clarification:
        state.final_text = clarification
        state.status = LoopStatus.COMPLETED
        state.transition = LoopTransitionReason.SHOULD_CONTINUE_FALSE
        loop.diagnostics["ask_clarification"] = True
        return False

    if loop.callbacks.should_continue:
        if not loop.callbacks.should_continue(state.iteration, response):
            state.final_text = response.content
            state.status = LoopStatus.COMPLETED
            state.transition = LoopTransitionReason.SHOULD_CONTINUE_FALSE
            return False

    state.transition = LoopTransitionReason.TOOL_BATCH_CONTINUE
    return True


def _get_stuck_message(loop: "AgentLoop") -> Optional[str]:
    """Return guardrail stuck message or None (best-effort)."""

    def _check() -> Optional[str]:
        return cast(Optional[str], guardrail_stuck_message(loop._guardrails))

    return cast(
        Optional[str],
        safe_best_effort(_check, label="agent_loop.stuck_check"),
    )


def _dispatch_text_response(
    loop: "AgentLoop",
    response: "NormalizedResponse",
    state: TurnBodyState,
    start_time: float,
    steer_session: str,
) -> None:
    """Text path: try truncation / stop-hook / budget continuation, else mark COMPLETED."""
    state.final_text = response.content
    state.final_reasoning = response.reasoning

    def _apply_grounding_gate() -> None:
        corrected = try_correct_ungrounded_list_reply(
            state.user_content,
            state.final_text,
            loop._messages,
        )
        if corrected:
            state.final_text = corrected
            loop.diagnostics["mcp_outbound_grounding"] = True

    safe_best_effort(_apply_grounding_gate, label="agent_loop.outbound_grounding")

    def _apply_output_grounding() -> None:
        state.final_text = apply_output_grounding(
            state.user_content,
            state.final_text,
            loop.diagnostics,
        )

    safe_best_effort(_apply_output_grounding, label="agent_loop.output_grounding")
    if _try_truncation_continue(loop, response, state):
        return
    if _try_stop_hook_continue(loop, state, start_time, steer_session):
        return
    if _try_budget_continue(loop, state):
        return
    state.status = LoopStatus.COMPLETED
    state.transition = LoopTransitionReason.TURN_COMPLETED


def _try_truncation_continue(
    loop: "AgentLoop",
    response: "NormalizedResponse",
    state: TurnBodyState,
) -> bool:
    """Check truncation continue; if triggered, set state and return True."""
    if not needs_truncation_continue(response):
        return False
    if loop._truncation_retries >= loop.config.max_truncation_continues:
        return False
    loop._truncation_retries += 1
    if state.final_text:
        msg = {"role": "assistant", "content": state.final_text}
        _store_reasoning_on_message(msg, state.final_reasoning)
        loop._messages.append(msg)
    loop._messages.append(
        {"role": "user", "content": truncation_continue_message()}
    )
    state.final_text = None
    state.transition = LoopTransitionReason.TRUNCATION_CONTINUE
    return True


def _try_stop_hook_continue(
    loop: "AgentLoop",
    state: TurnBodyState,
    start_time: float,
    steer_session: str,
) -> bool:
    """Check stop hook continue; if blocked, set state and return True."""
    stop_blocked = loop._maybe_stop_hook_continue(
        steer_session=steer_session,
        iteration=state.iteration,
        start_time=start_time,
        final_text=state.final_text or "",
    )
    if not stop_blocked:
        return False
    state.final_text = None
    state.transition = LoopTransitionReason.STOP_HOOK_BLOCKED
    return True


def _try_budget_continue(
    loop: "AgentLoop",
    state: TurnBodyState,
) -> bool:
    """Check budget continue; if triggered, set state and return True."""
    if state.budget_state is None:
        return False
    max_cont, min_delta = continuation_limits()
    if not state.budget_state.should_continue(
        loop._total_tokens,
        max_continuations=max_cont,
        min_delta_tokens=min_delta,
    ):
        return False
    if state.final_text:
        msg = {"role": "assistant", "content": state.final_text}
        _store_reasoning_on_message(msg, state.final_reasoning)
        loop._messages.append(msg)
    state.budget_state.record_continuation(loop._total_tokens)
    nudge = get_budget_continuation_message(
        state.budget_state.budget_tokens,
        attempt=state.budget_state.continuations_used,
    )
    loop._messages.append({"role": "user", "content": nudge})
    state.final_text = None
    state.transition = LoopTransitionReason.TOKEN_BUDGET_CONTINUE
    return True

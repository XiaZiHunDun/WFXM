"""Phase helpers extracted from ``AgentLoop._run_turn_body`` (R1-8 split).

Audit source: ``docs/reviews/project-deep-audit-2026-06-r1to8.md`` §R1-8

The original ``AgentLoop._run_turn_body`` (337 lines, lines 250-587) was a
god method that combined turn budget / callback / interrupt / token /
ephemeral / API / guardrail / tool batch / 压缩回退 — a 3.4x overrun of
the 100-line audit cap. Per the audit's recommendation, the body is
split into 4 thin phase orchestrators:

* :func:`_phase_init`            — state reset + turn budget + user message
* :func:`_phase_call_llm`        — pre-callbacks + nudge + LLM call + None
                                    handling + usage recording
* :func:`_phase_dispatch_tools`  — tool processing OR text response
                                    handling (truncation / stop-hook / budget)
* :func:`_phase_finalize`        — store final + transcript + metrics +
                                    stop hooks + LoopResult

And ``AgentLoop._prepare_user_message`` (53 lines, wider-contract add) is
split into 2 sub-phases:

* :func:`_phase_resolve_user_text` — sanitize + system reminder + append
* :func:`_phase_enrich_user_text`  — tool selection + transcript record

A mutable :class:`TurnBodyState` carrier threads per-turn state between
phases. Each phase helper is a thin orchestrator (< 50 source lines,
contract-enforced by ``tests/test_agent_loop_phase_split.py``). Long
bodies live in private helpers (``_emit_*`` / ``_inject_*`` /
``_mark_*`` / ``_record_*`` / ``_try_*`` / ``_store_*`` / ``_build_*``).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Optional

from butler.core.best_effort import safe_best_effort
from butler.core.loop_types import (
    LoopResult,
    LoopStatus,
    LoopTransitionReason,
)
from butler.core.message_sanitize import sanitize_surrogates

if TYPE_CHECKING:
    from butler.core.agent_loop import AgentLoop
    from butler.transport.types import NormalizedResponse

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Carrier — mutable per-turn state shared between phases.
# ---------------------------------------------------------------------------

@dataclass
class TurnBodyState:
    """Mutable carrier for one turn's body execution.

    Phases mutate fields on this object. The orchestrator initializes
    inputs in ``_phase_init`` and reads the final ``status`` /
    ``transition`` / ``final_text`` after ``_phase_finalize``.
    """

    # --- Set in _phase_init ------------------------------------------------
    original_config: Any = None  # LoopConfig snapshot
    budget_state: Any = None  # TurnBudgetState | None
    user_content: str = ""
    turn_tools: list[dict] = field(default_factory=list)

    # --- Per-iteration state ----------------------------------------------
    status: LoopStatus = LoopStatus.RUNNING
    transition: LoopTransitionReason = LoopTransitionReason.UNKNOWN
    iteration: int = 0

    # --- Final output (read by _phase_finalize) ---------------------------
    final_text: Optional[str] = None
    final_reasoning: Optional[str] = None


# ---------------------------------------------------------------------------
# Phase 1 — state init + turn budget + user message prep.
# ---------------------------------------------------------------------------

def _phase_init(
    loop: "AgentLoop",
    user_message: str,
    steer_session: str,
    state: TurnBodyState,
) -> None:
    """Phase 1: state reset + turn budget resolution + user message prep.

    Populates ``state.original_config``, ``state.budget_state``,
    ``state.user_content``, ``state.turn_tools`` and sets
    ``loop._turn_tools``.
    """
    loop._init_turn_state(steer_session)

    from butler.core.turn_token_budget import (
        TurnBudgetState,
        resolve_turn_budget,
    )

    state.original_config = loop.config
    loop.config, turn_budget_tokens, cleaned_user = resolve_turn_budget(
        user_message, loop.config,
    )
    if turn_budget_tokens:
        state.budget_state = TurnBudgetState(int(turn_budget_tokens))
        loop.diagnostics["turn_token_budget"] = int(turn_budget_tokens)
    else:
        state.budget_state = None

    state.user_content, state.turn_tools = loop._prepare_user_message(
        cleaned_user, steer_session,
    )
    loop._turn_tools = state.turn_tools

    from butler.core.best_effort import safe_best_effort

    def _inject_feedback() -> None:
        from butler.ops.eval_feedback import get_feedback_context

        feedback = get_feedback_context(lookback_hours=24.0)
        if feedback:
            loop._turn_ephemeral_system = (
                (loop._turn_ephemeral_system or "") + "\n" + feedback
            ).strip()
            loop.diagnostics["eval_feedback_injected"] = True

    safe_best_effort(_inject_feedback, label="agent_loop.eval_feedback")

    def _apply_hard_feedback() -> None:
        from butler.ops.eval_actions import apply_hard_feedback

        hard = apply_hard_feedback()
        if hard.get("applied"):
            loop.diagnostics["eval_hard_feedback"] = hard

    safe_best_effort(_apply_hard_feedback, label="agent_loop.hard_feedback")


# ---------------------------------------------------------------------------
# Per-iteration helpers — interrupt + compaction (called by orchestrator).
# ---------------------------------------------------------------------------

def _mark_interrupted_status(state: TurnBodyState) -> None:
    """Set state.status/transition when interrupt was detected pre-iteration."""
    state.status = LoopStatus.INTERRUPTED
    state.transition = LoopTransitionReason.INTERRUPTED


def _phase_maybe_compact_turn(
    loop: "AgentLoop",
    state: TurnBodyState,
) -> bool:
    """Run explicit compaction turn; return True if compacted (caller skips).

    Wrapped in try/except by the caller — best-effort, never raises.
    """
    from butler.core.compaction_task import (
        run_compaction_turn,
        should_run_compaction_turn,
    )
    from butler.execution_context import get_audit_session_key

    if not should_run_compaction_turn(
        loop._messages,
        max_context_tokens=loop.config.max_context_tokens,
        estimate_tokens=loop._estimate_tokens,
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
        session_key=get_audit_session_key(fallback="default"),
    )
    if not did_compact:
        return False
    loop._messages[:] = new_msgs
    from butler.core.best_effort import safe_best_effort

    def _apply_followup() -> None:
        from butler.core.compaction_steer_bridge import apply_compaction_turn_followup
        from butler.execution_context import get_audit_session_key

        sk = get_audit_session_key(fallback="default")
        loop._messages[:] = apply_compaction_turn_followup(
            loop._messages, sk, loop.diagnostics,
        )

    safe_best_effort(_apply_followup, label="agent_loop.compaction_followup")
    state.transition = LoopTransitionReason.COMPACTION_TURN
    return True


# ---------------------------------------------------------------------------
# Phase 2 — pre-callbacks + budget nudge + LLM call + None handling + usage.
# ---------------------------------------------------------------------------

def _phase_call_llm(
    loop: "AgentLoop",
    state: TurnBodyState,
) -> Optional["NormalizedResponse"]:
    """Phase 2: LLM call with pre-callbacks, nudge, None handling, usage.

    Returns the LLM response, or ``None`` when the call yielded no
    response (interrupted / error) — in which case ``state.status`` and
    ``state.transition`` are set and the loop should break.
    """
    _emit_iteration_callbacks(loop, state)
    _inject_budget_nudge(loop, state)
    response = loop._call_llm_with_retry()
    if response is None:
        _mark_no_response(loop, state)
        return None
    _record_usage(loop, response, state)
    try:
        from butler.core.reasoning_trace import maybe_record_llm_reasoning

        maybe_record_llm_reasoning(loop, response, iteration=state.iteration)
    except Exception as exc:  # noqa: BLE001 — best-effort observability
        logger.debug("Reasoning trace skipped: %s", exc)
    return response


def _emit_iteration_callbacks(loop: "AgentLoop", state: TurnBodyState) -> None:
    """Emit stream-boundary (iteration > 1) and on_iteration callbacks."""
    if state.iteration > 1 and loop.callbacks.on_stream_boundary:
        loop.callbacks.on_stream_boundary()
    if loop.callbacks.on_iteration:
        loop.callbacks.on_iteration(state.iteration, state.status)


def _inject_budget_nudge(loop: "AgentLoop", state: TurnBodyState) -> None:
    """Inject loop budget nudge messages (best-effort)."""
    try:
        from butler.core.loop_budget_nudge import maybe_inject_loop_budget_nudges

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
    except Exception as exc:  # noqa: BLE001 — best-effort nudge
        logger.warning("Loop budget nudge skipped: %s", exc)


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
    from butler.core.context_budget import (
        record_usage_in_diagnostics,
        usage_billable_tokens,
    )
    from butler.transport.usage_normalize import normalize_usage

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
        from butler.ops.cost_tracker import get_session_cost
        from butler.execution_context import get_current_session_key

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


# ---------------------------------------------------------------------------
# Phase 3 — tool processing OR text response handling.
# ---------------------------------------------------------------------------

def _phase_dispatch_tools(
    loop: "AgentLoop",
    response: "NormalizedResponse",
    state: TurnBodyState,
    start_time: float,
    steer_session: str,
) -> bool:
    """Phase 3: dispatch LLM response. Returns True to continue, False to break.

    For tool responses: process tools and check waiting/stuck/clarification/
    should_continue (any of which terminates the loop). For text responses:
    try truncation / stop-hook / budget continuation (any of which continues
    the loop). Otherwise mark the turn COMPLETED.
    """
    if response.tool_calls:
        return _dispatch_tool_response(loop, response, state)
    _dispatch_text_response(loop, response, state, start_time, steer_session)
    return state.status == LoopStatus.RUNNING


def _dispatch_tool_response(
    loop: "AgentLoop",
    response: "NormalizedResponse",
    state: TurnBodyState,
) -> bool:
    """Tool path: process tool calls, then check early-termination signals.

    Returns True to continue the loop, False when an early-termination
    signal (waiting_confirmation / stuck / clarification / should_continue)
    was detected.
    """
    batch_stats = loop._process_tool_calls(response)

    def _try_github_repo_direct() -> bool:
        from butler.mcp.github_grounding import try_github_repo_list_direct_reply

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
        from butler.mcp.github_grounding import try_github_issue_list_direct_reply

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
        from butler.mcp.todoist_grounding import try_todoist_project_list_direct_reply

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
            from butler.core.reasoning_trace import record_stuck_reflect

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
        from butler.core.loop_stuck import guardrail_stuck_message

        return guardrail_stuck_message(loop._guardrails)

    return safe_best_effort(_check, label="agent_loop.stuck_check")


def _dispatch_text_response(
    loop: "AgentLoop",
    response: "NormalizedResponse",
    state: TurnBodyState,
    start_time: float,
    steer_session: str,
) -> None:
    """Text path: try truncation / stop-hook / budget continuation, else
    mark the turn COMPLETED. Mutates ``state`` in place; the caller reads
    ``state.status`` to decide whether to keep looping.
    """
    state.final_text = response.content
    state.final_reasoning = response.reasoning
    def _apply_grounding_gate() -> None:
        from butler.mcp.outbound_grounding_gate import try_correct_ungrounded_list_reply

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
        from butler.core.output_grounding import apply_output_grounding

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
    from butler.core.loop_response import (
        needs_truncation_continue,
        truncation_continue_message,
    )
    from butler.transport.reasoning_replay import store_reasoning_on_message

    if not needs_truncation_continue(response):
        return False
    if loop._truncation_retries >= loop.config.max_truncation_continues:
        return False
    loop._truncation_retries += 1
    if state.final_text:
        msg = {"role": "assistant", "content": state.final_text}
        store_reasoning_on_message(msg, state.final_reasoning)
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
    from butler.core.turn_token_budget import (
        continuation_limits,
        get_budget_continuation_message,
    )
    from butler.transport.reasoning_replay import store_reasoning_on_message

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
        store_reasoning_on_message(msg, state.final_reasoning)
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


# ---------------------------------------------------------------------------
# Phase 4 — post-loop wrap-up: store final, metrics, stop hooks, LoopResult.
# ---------------------------------------------------------------------------

def _phase_finalize(
    loop: "AgentLoop",
    state: TurnBodyState,
    run_callbacks: Any,
    steer_session: str,
    start_time: float,
) -> LoopResult:
    """Phase 4: store final assistant message, record metrics, run stop
    hooks, build and return the ``LoopResult``.
    """
    if state.status == LoopStatus.RUNNING:
        state.status = LoopStatus.TOOL_LIMIT
        state.transition = LoopTransitionReason.TOOL_LIMIT
    if state.final_text:
        _store_final_message(loop, state, steer_session)
    elapsed = time.time() - start_time
    loop.diagnostics["loop_transition_reason"] = state.transition.value
    _record_turn_metrics(loop, state, elapsed, steer_session)
    return _build_loop_result(loop, state, run_callbacks, steer_session, elapsed)


def _store_final_message(
    loop: "AgentLoop",
    state: TurnBodyState,
    steer_session: str,
) -> None:
    """Append final assistant message + record transcript (best-effort)."""
    from butler.core.session_transcript import record_assistant_message
    from butler.transport.reasoning_replay import store_reasoning_on_message

    msg = {"role": "assistant", "content": state.final_text}
    store_reasoning_on_message(msg, state.final_reasoning)
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
        from butler.ops.runtime_metrics import inc, observe_ms

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
    """Run post-run stop hooks if status is COMPLETED and no prior stop-hook
    context exists (best-effort)."""
    if loop.diagnostics.get("stop_hook_context"):
        logger.debug("Stop hook context already present, skipping post-run hooks")
        return
    if state.status != LoopStatus.COMPLETED:
        return
    def _run_hooks() -> None:
        from butler.hooks.runner import run_stop_hooks

        stop_hooks = run_stop_hooks(
            status=state.status.value,
            last_assistant_message=state.final_text or "",
            session_key=steer_session,
            iterations=state.iteration,
            tool_calls=loop._tool_calls_count,
            elapsed_seconds=result.elapsed_seconds,
        )
        if stop_hooks.additional_context:
            loop.diagnostics["stop_hook_context"] = list(
                stop_hooks.additional_context
            )

    safe_best_effort(_run_hooks, label="agent_loop.stop_hooks")


# ---------------------------------------------------------------------------
# User-message sub-phases (wider-contract add, R1-5.2 lesson).
# ---------------------------------------------------------------------------

def _phase_resolve_user_text(
    loop: "AgentLoop",
    user_message: str,
) -> str:
    """Phase U1: inject system prompt (first turn), sanitize, prepend
    system reminder, append user message to ``loop._messages``.

    Returns the sanitized + reminder-enriched user content.
    """
    if not loop._messages:
        if loop.system_prompt:
            loop._messages.append(
                {"role": "system", "content": loop.system_prompt}
            )

    user_content = sanitize_surrogates(user_message)
    def _prepend_reminder() -> str:
        from butler.core.system_reminder import maybe_prepend_system_reminder

        return maybe_prepend_system_reminder(user_content)

    reminded = safe_best_effort(
        _prepend_reminder,
        label="agent_loop.system_reminder",
        default=user_content,
    )
    if reminded is not None:
        user_content = reminded
    loop._messages.append({"role": "user", "content": user_content})
    return user_content


def _prepare_skill_tool_context(
    loop: "AgentLoop",
    user_content: str,
    steer_session: str,
    turn_tools: list,
) -> tuple[set[str], list]:
    skill_pt: set[str] = set()
    try:
        from butler.core.skill_tool_bridge import collect_pinned_tools

        skill_pt, exp_mcp = collect_pinned_tools(user_content)
        if exp_mcp:
            try:
                from butler.core.harness_flags import (
                    mcp_deferred_same_turn_enabled,
                    mcp_deferred_tools_enabled,
                )
                from butler.mcp.deferred import (
                    merge_deferred_mcp_into_turn_tools,
                    promote_experience_mcp_tools,
                )

                if mcp_deferred_tools_enabled():
                    added, rejected = promote_experience_mcp_tools(
                        exp_mcp,
                        session_key=steer_session,
                    )
                    if added:
                        loop.diagnostics["experience_mcp_promoted"] = len(added)
                        try:
                            from butler.ops.runtime_metrics import inc

                            inc(
                                "execution_pointer_pin",
                                value=len(added),
                                labels={"source": "experience_mcp"},
                                session_key=steer_session,
                            )
                        except Exception:  # noqa: BLE001 — metrics optional
                            pass
                    if rejected:
                        loop.diagnostics["experience_mcp_rejected"] = rejected
                    if added and mcp_deferred_same_turn_enabled():
                        turn_tools = merge_deferred_mcp_into_turn_tools(
                            turn_tools,
                            session_key=steer_session,
                        )
                        loop.diagnostics["experience_mcp_same_turn"] = len(added)
            except Exception as mcp_exc:  # noqa: BLE001 — best-effort promote
                logger.debug("Experience MCP promote skipped: %s", mcp_exc)
        if skill_pt:
            loop.diagnostics["experience_pinned_tools"] = len(skill_pt)
    except Exception as exc:  # noqa: BLE001 — best-effort extraction
        logger.warning("Skill preferred tools extraction skipped: %s", exc)
    return skill_pt, turn_tools


def _phase_enrich_user_text(
    loop: "AgentLoop",
    user_content: str,
    steer_session: str,
) -> list[dict]:
    """Phase U2: tool selection (per-turn) + record user message transcript.

    Returns the turn-specific tool list (possibly narrowed from
    ``loop.tools`` by the selector).
    """
    turn_tools = list(loop.tools or [])
    try:
        from butler.core.tool_selector import select_tools_for_context

        skill_pt, turn_tools = _prepare_skill_tool_context(
            loop, user_content, steer_session, turn_tools,
        )

        selected, sel_diag = select_tools_for_context(
            turn_tools,
            user_hint=user_content,
            skill_preferred_tools=skill_pt or None,
        )
        turn_tools = list(selected)
        for key, val in sel_diag.items():
            loop.diagnostics[key] = val
    except Exception as exc:  # noqa: BLE001 — best-effort selector
        logger.warning("Tool selector skipped: %s", exc)

    def _record_user() -> None:
        from butler.core.session_transcript import record_user_message

        record_user_message(steer_session, user_content)

    safe_best_effort(_record_user, label="agent_loop.transcript_user")

    return turn_tools


__all__ = [
    "TurnBodyState",
    "_phase_init",
    "_phase_call_llm",
    "_phase_dispatch_tools",
    "_phase_finalize",
    "_phase_maybe_compact_turn",
    "_mark_interrupted_status",
    "_phase_resolve_user_text",
    "_phase_enrich_user_text",
]

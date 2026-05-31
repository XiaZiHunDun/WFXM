"""Turn body execution — extracted from AgentLoop for module size reduction."""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)


def run_turn_body(
    loop,
    user_message: str,
    *,
    run_callbacks,
    saved_callbacks,
    pre_run_diagnostics: dict[str, Any],
    start_time: float,
    steer_session: str,
):
    from butler.core.loop_types import (
        LoopResult,
        LoopStatus,
        LoopTransitionReason,
    )

    loop._init_turn_state(steer_session)

    from butler.core.turn_token_budget import (
        TurnBudgetState,
        continuation_limits,
        get_budget_continuation_message,
        resolve_turn_budget,
    )

    original_config = loop.config
    loop.config, turn_budget_tokens, cleaned_user = resolve_turn_budget(
        user_message,
        loop.config,
    )
    budget_state: TurnBudgetState | None = (
        TurnBudgetState(int(turn_budget_tokens))
        if turn_budget_tokens
        else None
    )
    if turn_budget_tokens:
        loop.diagnostics["turn_token_budget"] = int(turn_budget_tokens)

    user_content, turn_tools = loop._prepare_user_message(cleaned_user, steer_session)
    loop._turn_tools = turn_tools

    final_text = None
    final_reasoning = None
    status = LoopStatus.RUNNING
    transition = LoopTransitionReason.UNKNOWN
    iteration = 0

    from butler.core.delegate_context import set_parent_messages
    from butler.core.loop_response import needs_truncation_continue
    from butler.tools.interrupt import is_interrupted

    try:
        while status == LoopStatus.RUNNING and iteration < loop.config.max_iterations:
            if loop._interrupted or (loop._thread_id and is_interrupted(loop._thread_id)):
                status = LoopStatus.INTERRUPTED
                transition = LoopTransitionReason.INTERRUPTED
                break

            iteration += 1
            set_parent_messages(loop._messages)
            try:
                from butler.core.compaction_task import (
                    run_compaction_turn,
                    should_run_compaction_turn,
                )
                from butler.execution_context import get_audit_session_key

                if should_run_compaction_turn(
                    loop._messages,
                    max_context_tokens=loop.config.max_context_tokens,
                    estimate_tokens=loop._estimate_tokens,
                    diagnostics=loop.diagnostics,
                    iteration=iteration,
                    max_output_tokens=getattr(loop.config, "max_output_tokens", None),
                ):
                    did_compact, new_msgs = run_compaction_turn(
                        loop._messages,
                        compress=loop._compress_context,
                        diagnostics=loop.diagnostics,
                        iteration=iteration,
                        session_key=get_audit_session_key(fallback="default"),
                    )
                    if did_compact:
                        loop._messages[:] = new_msgs
                        try:
                            from butler.core.compaction_steer_bridge import (
                                apply_compaction_turn_followup,
                            )
                            from butler.execution_context import get_audit_session_key

                            sk = get_audit_session_key(fallback="default")
                            loop._messages[:] = apply_compaction_turn_followup(
                                loop._messages,
                                sk,
                                loop.diagnostics,
                            )
                        except Exception as exc:
                            logger.debug("Compaction turn followup skipped: %s", exc, exc_info=True)
                        transition = LoopTransitionReason.COMPACTION_TURN
                        continue
            except Exception as exc:
                logger.debug("Explicit compaction turn skipped: %s", exc, exc_info=True)

            if iteration > 1 and loop.callbacks.on_stream_boundary:
                loop.callbacks.on_stream_boundary()
            if loop.callbacks.on_iteration:
                loop.callbacks.on_iteration(iteration, status)

            try:
                from butler.core.loop_budget_nudge import maybe_inject_loop_budget_nudges

                budget_tokens = (
                    int(budget_state.budget_tokens) if budget_state is not None else None
                )
                maybe_inject_loop_budget_nudges(
                    loop._messages,
                    loop.diagnostics,
                    iteration=iteration,
                    max_iterations=loop.config.max_iterations,
                    total_tokens=loop._total_tokens,
                    budget_tokens=budget_tokens,
                )
            except Exception as exc:
                logger.warning("Loop budget nudge skipped: %s", exc)

            response = loop._call_llm_with_retry()
            if response is None:
                if loop._interrupted:
                    status = LoopStatus.INTERRUPTED
                    transition = LoopTransitionReason.INTERRUPTED
                else:
                    status = LoopStatus.ERROR
                    if loop.diagnostics.get("reactive_context_compact"):
                        transition = LoopTransitionReason.REACTIVE_COMPACT_RETRY
                    else:
                        transition = LoopTransitionReason.LLM_ERROR
                break

            if response.usage:
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

            if response.tool_calls:
                batch_stats = loop._process_tool_calls(response)
                if getattr(batch_stats, "waiting_confirmation_message", None):
                    final_text = batch_stats.waiting_confirmation_message
                    status = LoopStatus.WAITING_CONFIRMATION
                    transition = LoopTransitionReason.WAITING_CONFIRMATION
                    loop.diagnostics["two_phase_confirm"] = True
                    break
                stuck_msg = None
                try:
                    from butler.core.loop_stuck import guardrail_stuck_message

                    stuck_msg = guardrail_stuck_message(loop._guardrails)
                except Exception as exc:
                    logger.warning("Stuck message check skipped: %s", exc)
                if stuck_msg:
                    final_text = stuck_msg
                    status = LoopStatus.STUCK
                    transition = LoopTransitionReason.STUCK
                    loop.diagnostics["loop_stuck"] = True
                    break
                if getattr(batch_stats, "clarification_question", None):
                    final_text = batch_stats.clarification_question
                    status = LoopStatus.COMPLETED
                    transition = LoopTransitionReason.SHOULD_CONTINUE_FALSE
                    loop.diagnostics["ask_clarification"] = True
                    break
                if loop.callbacks.should_continue:
                    if not loop.callbacks.should_continue(iteration, response):
                        final_text = response.content
                        status = LoopStatus.COMPLETED
                        transition = LoopTransitionReason.SHOULD_CONTINUE_FALSE
                        break
                transition = LoopTransitionReason.TOOL_BATCH_CONTINUE
                continue

            final_text = response.content
            final_reasoning = response.reasoning
            if (
                needs_truncation_continue(response)
                and loop._truncation_retries < loop.config.max_truncation_continues
            ):
                loop._truncation_retries += 1
                if final_text:
                    msg = {"role": "assistant", "content": final_text}
                    from butler.transport.reasoning_replay import store_reasoning_on_message

                    store_reasoning_on_message(msg, final_reasoning)
                    loop._messages.append(msg)
                from butler.core.loop_response import truncation_continue_message

                loop._messages.append({"role": "user", "content": truncation_continue_message()})
                final_text = None
                transition = LoopTransitionReason.TRUNCATION_CONTINUE
                continue

            stop_blocked = maybe_stop_hook_continue(
                loop,
                steer_session=steer_session,
                iteration=iteration,
                start_time=start_time,
                final_text=final_text or "",
            )
            if stop_blocked:
                final_text = None
                transition = LoopTransitionReason.STOP_HOOK_BLOCKED
                continue

            if budget_state is not None:
                max_cont, min_delta = continuation_limits()
                if budget_state.should_continue(
                    loop._total_tokens,
                    max_continuations=max_cont,
                    min_delta_tokens=min_delta,
                ):
                    if final_text:
                        msg = {"role": "assistant", "content": final_text}
                        from butler.transport.reasoning_replay import store_reasoning_on_message

                        store_reasoning_on_message(msg, final_reasoning)
                        loop._messages.append(msg)
                    budget_state.record_continuation(loop._total_tokens)
                    nudge = get_budget_continuation_message(
                        budget_state.budget_tokens,
                        attempt=budget_state.continuations_used,
                    )
                    loop._messages.append({"role": "user", "content": nudge})
                    final_text = None
                    transition = LoopTransitionReason.TOKEN_BUDGET_CONTINUE
                    continue

            status = LoopStatus.COMPLETED
            transition = LoopTransitionReason.TURN_COMPLETED

        if status == LoopStatus.RUNNING:
            status = LoopStatus.TOOL_LIMIT
            transition = LoopTransitionReason.TOOL_LIMIT

        if final_text:
            msg = {"role": "assistant", "content": final_text}
            from butler.transport.reasoning_replay import store_reasoning_on_message

            store_reasoning_on_message(msg, final_reasoning)
            loop._messages.append(msg)
            try:
                from butler.core.session_transcript import record_assistant_message

                record_assistant_message(
                    steer_session,
                    final_text,
                    tool_calls=loop._tool_calls_count,
                )
            except Exception as exc:
                logger.debug("Assistant transcript record skipped: %s", exc, exc_info=True)

    finally:
        loop.config = original_config
        loop._restore_primary_client()
        loop._turn_tools = None
        from butler.core.delegate_context import set_parent_callbacks

        set_parent_callbacks(None)
        if run_callbacks is not None:
            loop.callbacks = saved_callbacks

    elapsed = time.time() - start_time
    loop.diagnostics["loop_transition_reason"] = transition.value
    try:
        from butler.ops.runtime_metrics import inc, observe_ms

        observe_ms(
            "turn_duration",
            elapsed * 1000.0,
            labels={
                "transition": str(transition.value)[:32],
                "status": str(status.value)[:16],
            },
            session_key=steer_session,
        )
        inc(
            "turn_finished",
            labels={
                "transition": str(transition.value)[:32],
                "status": str(status.value)[:16],
            },
            session_key=steer_session,
        )
    except Exception as exc:
        logger.warning("Turn metrics recording skipped: %s", exc, exc_info=True)
    result = LoopResult(
        status=status,
        transition_reason=transition.value,
        final_response=final_text,
        reasoning=final_reasoning,
        messages=list(loop._messages),
        iterations=iteration,
        total_tokens=loop._total_tokens,
        tool_calls_made=loop._tool_calls_count,
        elapsed_seconds=elapsed,
        diagnostics=dict(loop.diagnostics),
    )
    if loop.diagnostics.get("stop_hook_context"):
        logger.debug("Stop hook context already present, skipping post-run hooks")
    elif status == LoopStatus.COMPLETED:
        try:
            from butler.hooks.runner import run_stop_hooks

            stop_hooks = run_stop_hooks(
                status=status.value,
                last_assistant_message=final_text or "",
                session_key=steer_session,
                iterations=iteration,
                tool_calls=loop._tool_calls_count,
                elapsed_seconds=elapsed,
            )
            if stop_hooks.additional_context:
                loop.diagnostics["stop_hook_context"] = list(
                    stop_hooks.additional_context
                )
        except Exception as exc:
            logger.debug("Stop hooks context skipped: %s", exc, exc_info=True)
    return result


def maybe_stop_hook_continue(
    loop,
    *,
    steer_session: str,
    iteration: int,
    start_time: float,
    final_text: str,
) -> bool:
    """Run Stop hooks inside the loop; return True if continuation was injected."""
    from butler.core.loop_types import LoopStatus

    try:
        from butler.hooks.runner import run_stop_hooks

        stop_hooks = run_stop_hooks(
            status=LoopStatus.RUNNING.value,
            last_assistant_message=final_text,
            session_key=steer_session,
            iterations=iteration,
            tool_calls=loop._tool_calls_count,
            elapsed_seconds=time.time() - start_time,
        )
    except Exception as exc:
        logger.debug("Stop hooks skipped: %s", exc, exc_info=True)
        return False

    if stop_hooks.additional_context:
        loop.diagnostics["stop_hook_context"] = list(stop_hooks.additional_context)

    if not stop_hooks.blocked:
        return False

    loop.diagnostics["stop_hook_blocked"] = True
    block_msg = (stop_hooks.block_message or "Stop hook 要求继续处理").strip()
    if final_text:
        msg = {"role": "assistant", "content": final_text}
        loop._messages.append(msg)
    loop._messages.append({
        "role": "user",
        "content": f"[stop-hook-block]\n{block_msg}",
    })
    return True

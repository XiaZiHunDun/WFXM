"""Butler Agent Loop — the core LLM conversation engine."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Optional

from butler.core.context_pipeline import ContextPipeline
from butler.core.delegate_context import set_parent_callbacks
from butler.core.llm_retry import call_llm_with_retry
from butler.core.loop_response import (
    needs_truncation_continue,
    truncation_continue_message,
)
from butler.core.loop_types import (
    LoopCallbacks,
    LoopConfig,
    LoopResult,
    LoopStatus,
    LoopTransitionReason,
)
from butler.core.message_sanitize import sanitize_surrogates
from butler.core.tool_batch import dispatch_tool_with_envelope, process_tool_calls
from butler.tool_guardrails import ToolCallGuardrailController
from butler.tools.interrupt import clear_interrupt, is_interrupted, set_interrupt
from butler.core.steer import clear_steer, mark_run_active, mark_run_inactive
from butler.transport.base import LLMClientProtocol
from butler.transport.fallback import FallbackEntry, create_client_from_entry
from butler.transport.llm_client import LLMClient
from butler.transport.types import NormalizedResponse

logger = logging.getLogger(__name__)


def _doom_loop_block_on_ask(
    decision: GuardrailDecision,
    tool_name: str,
    args: dict,
) -> str | None:
    """Resolve doom-loop ask-mode for a prefetched tool call.

    Returns a synthetic_result JSON (blocked) when the user has not approved the
    call, and ``None`` when the call is approved and should be dispatched.
    Fails CLOSED: any exception raised while checking the approval cache is
    logged and treated as a block rather than silently allowed.
    """
    try:
        from butler.permissions.doom_loop import check_doom_loop_ask

        if check_doom_loop_ask(decision, tool_name, args):
            from butler.tool_guardrails import synthetic_result

            return synthetic_result(decision)
    except Exception:
        logger.exception(
            "Doom-loop ask check failed; failing closed (synthetic block) for %s",
            tool_name,
        )
        from butler.tool_guardrails import synthetic_result

        return synthetic_result(decision)
    return None


class AgentLoop:
    """Self-contained LLM conversation loop with tool calling."""

    def __init__(
        self,
        client: LLMClientProtocol,
        *,
        system_prompt: str = "",
        tools: Optional[list[dict]] = None,
        tool_dispatcher: Optional[Callable[[str, dict], str]] = None,
        config: Optional[LoopConfig] = None,
        callbacks: Optional[LoopCallbacks] = None,
    ):
        self.client: LLMClientProtocol = client
        self.system_prompt = system_prompt
        self.tools = tools or []
        self.tool_dispatcher = tool_dispatcher
        self.config = config or LoopConfig()
        self.callbacks = callbacks or LoopCallbacks()

        self._messages: list[dict] = []
        self._turn_tools: list[dict] | None = None
        self._interrupted = False
        self._total_tokens = 0
        self._tool_calls_count = 0
        self._guardrails = ToolCallGuardrailController() if self.config.enable_guardrails else None
        self._context = ContextPipeline(self.config)
        self._context.attach_loop(self)
        self._turn_ephemeral_system: str | None = None
        self._thread_id: int | None = None
        _chain = list(self.config.fallback_entries or [])
        try:
            from butler.transport.provider_health import filter_fallback_chain

            _chain = filter_fallback_chain(_chain)
        except Exception as exc:
            logger.debug("Fallback chain filter skipped: %s", exc, exc_info=True)
        self._fallback_chain: list[FallbackEntry] = _chain
        self._fallback_index = 0
        self._primary_client: LLMClient | None = None
        self._empty_retries = 0
        self._truncation_retries = 0
        self.diagnostics: dict[str, Any] = {}
        self._tool_prefetch: dict[str, str] = {}
        from butler.core.loop_plugins import default_plugin_registry

        self._plugins = default_plugin_registry(self.config)

    @property
    def _compression_summary(self) -> str:
        return self._context.compression_summary

    @_compression_summary.setter
    def _compression_summary(self, value: str) -> None:
        self._context.compression_summary = value

    def interrupt(self) -> None:
        self._interrupted = True
        if self._thread_id is not None:
            set_interrupt(True, self._thread_id)

    def clear_interrupt(self) -> None:
        self._interrupted = False
        if self._thread_id is not None:
            clear_interrupt(self._thread_id)

    def run(
        self,
        user_message: str,
        *,
        run_callbacks: Optional[LoopCallbacks] = None,
        ephemeral_system: str | None = None,
    ) -> LoopResult:
        start_time = time.time()
        saved_callbacks = self.callbacks
        if run_callbacks is not None:
            from butler.core.loop_callbacks_merge import merge_loop_callbacks

            self.callbacks = merge_loop_callbacks(saved_callbacks, run_callbacks)
        pre_run_diagnostics = {
            k: v for k, v in self.diagnostics.items()
            if str(k).startswith("hygiene_")
        }
        self.diagnostics = dict(pre_run_diagnostics)
        self._turn_ephemeral_system = (ephemeral_system or "").strip() or None
        if self._turn_ephemeral_system:
            self.diagnostics["ephemeral_system_injected"] = True
        self._interrupted = False
        self._thread_id = threading.get_ident() if hasattr(threading, "get_ident") else None
        clear_interrupt(self._thread_id)
        from butler.execution_context import get_current_session_key

        _steer_session = get_current_session_key() or "default"
        mark_run_active(_steer_session)
        # PERF-13-3: 把整轮所有 record_* 批量成 1 次 flush
        from butler.core.session_transcript import transcript_batch

        try:
            with transcript_batch(_steer_session):
                return self._run_turn_body(
                    user_message,
                    run_callbacks=run_callbacks,
                    saved_callbacks=saved_callbacks,
                    pre_run_diagnostics=pre_run_diagnostics,
                    start_time=start_time,
                    steer_session=_steer_session,
                )
        finally:
            mark_run_inactive(_steer_session)

    def _init_turn_state(self, steer_session: str) -> None:
        """Reset per-turn mutable state before the iteration loop."""
        clear_steer(steer_session)
        self._primary_client = self.client
        self._fallback_index = 0
        self._empty_retries = 0
        self._truncation_retries = 0
        set_parent_callbacks(self.callbacks)
        from butler.core.delegate_context import set_parent_messages, set_parent_system_prompt

        set_parent_system_prompt(self.system_prompt)
        set_parent_messages(self._messages)
        self._tool_prefetch.clear()
        if self._guardrails:
            self._guardrails.reset_for_turn()
        from butler.core.tool_call_limits import reset_tool_call_limiter_for_turn

        reset_tool_call_limiter_for_turn()

    def _prepare_user_message(
        self,
        user_message: str,
        steer_session: str,
    ) -> tuple[str, list[dict]]:
        """Sanitize user input, select tools, record transcript.

        Returns ``(user_content, turn_tools)``.
        """
        if not self._messages:
            if self.system_prompt:
                self._messages.append({"role": "system", "content": self.system_prompt})

        user_content = sanitize_surrogates(user_message)
        try:
            from butler.core.system_reminder import maybe_prepend_system_reminder

            user_content = maybe_prepend_system_reminder(user_content)
        except Exception as exc:
            logger.warning("System reminder skipped: %s", exc)
        self._messages.append({"role": "user", "content": user_content})

        turn_tools = list(self.tools or [])
        try:
            from butler.core.tool_selector import select_tools_for_context

            skill_pt: set[str] = set()
            try:
                from butler.core.skill_tool_bridge import extract_skill_preferred_tools

                skill_pt = extract_skill_preferred_tools(user_content)
            except Exception as exc:
                logger.warning("Skill preferred tools extraction skipped: %s", exc)

            selected, sel_diag = select_tools_for_context(
                turn_tools,
                user_hint=user_content,
                skill_preferred_tools=skill_pt or None,
            )
            turn_tools = list(selected)
            for key, val in sel_diag.items():
                self.diagnostics[key] = val
        except Exception as exc:
            logger.warning("Tool selector skipped: %s", exc)

        try:
            from butler.core.session_transcript import record_user_message

            record_user_message(steer_session, user_content)
        except Exception as exc:
            logger.debug("Session transcript record skipped: %s", exc, exc_info=True)

        return user_content, turn_tools

    def _run_turn_body(
        self,
        user_message: str,
        *,
        run_callbacks: Optional[LoopCallbacks],
        saved_callbacks: LoopCallbacks,
        pre_run_diagnostics: dict[str, Any],
        start_time: float,
        steer_session: str,
    ) -> LoopResult:
        self._init_turn_state(steer_session)

        from butler.core.turn_token_budget import (
            TurnBudgetState,
            continuation_limits,
            get_budget_continuation_message,
            resolve_turn_budget,
        )

        original_config = self.config
        self.config, turn_budget_tokens, cleaned_user = resolve_turn_budget(
            user_message,
            self.config,
        )
        budget_state: TurnBudgetState | None = (
            TurnBudgetState(int(turn_budget_tokens))
            if turn_budget_tokens
            else None
        )
        if turn_budget_tokens:
            self.diagnostics["turn_token_budget"] = int(turn_budget_tokens)

        user_content, turn_tools = self._prepare_user_message(cleaned_user, steer_session)
        self._turn_tools = turn_tools

        final_text = None
        final_reasoning = None
        status = LoopStatus.RUNNING
        transition = LoopTransitionReason.UNKNOWN
        iteration = 0

        from butler.core.delegate_context import set_parent_messages

        try:
            while status == LoopStatus.RUNNING and iteration < self.config.max_iterations:
                if self._interrupted or (self._thread_id and is_interrupted(self._thread_id)):
                    status = LoopStatus.INTERRUPTED
                    transition = LoopTransitionReason.INTERRUPTED
                    break

                iteration += 1
                set_parent_messages(self._messages)
                try:
                    from butler.core.compaction_task import (
                        run_compaction_turn,
                        should_run_compaction_turn,
                    )
                    from butler.execution_context import get_audit_session_key

                    if should_run_compaction_turn(
                        self._messages,
                        max_context_tokens=self.config.max_context_tokens,
                        estimate_tokens=self._estimate_tokens,
                        diagnostics=self.diagnostics,
                        iteration=iteration,
                        max_output_tokens=getattr(self.config, "max_output_tokens", None),
                    ):
                        did_compact, new_msgs = run_compaction_turn(
                            self._messages,
                            compress=self._compress_context,
                            diagnostics=self.diagnostics,
                            iteration=iteration,
                            session_key=get_audit_session_key(fallback="default"),
                        )
                        if did_compact:
                            self._messages[:] = new_msgs
                            try:
                                from butler.core.compaction_steer_bridge import (
                                    apply_compaction_turn_followup,
                                )
                                from butler.execution_context import get_audit_session_key

                                sk = get_audit_session_key(fallback="default")
                                self._messages[:] = apply_compaction_turn_followup(
                                    self._messages,
                                    sk,
                                    self.diagnostics,
                                )
                            except Exception as exc:
                                logger.debug("Compaction turn followup skipped: %s", exc, exc_info=True)
                            transition = LoopTransitionReason.COMPACTION_TURN
                            continue
                except Exception as exc:
                    logger.debug("Explicit compaction turn skipped: %s", exc, exc_info=True)

                if iteration > 1 and self.callbacks.on_stream_boundary:
                    self.callbacks.on_stream_boundary()
                if self.callbacks.on_iteration:
                    self.callbacks.on_iteration(iteration, status)

                try:
                    from butler.core.loop_budget_nudge import maybe_inject_loop_budget_nudges

                    budget_tokens = (
                        int(budget_state.budget_tokens) if budget_state is not None else None
                    )
                    maybe_inject_loop_budget_nudges(
                        self._messages,
                        self.diagnostics,
                        iteration=iteration,
                        max_iterations=self.config.max_iterations,
                        total_tokens=self._total_tokens,
                        budget_tokens=budget_tokens,
                    )
                except Exception as exc:
                    logger.warning("Loop budget nudge skipped: %s", exc)

                response = self._call_llm_with_retry()
                if response is None:
                    if self._interrupted:
                        status = LoopStatus.INTERRUPTED
                        transition = LoopTransitionReason.INTERRUPTED
                    else:
                        status = LoopStatus.ERROR
                        if self.diagnostics.get("reactive_context_compact"):
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

                    provider = str(getattr(self.client, "provider_name", "") or "")
                    self.diagnostics["last_provider"] = provider
                    self.diagnostics["last_model"] = str(
                        getattr(self.client, "model_name", "") or ""
                    )
                    norm_usage = normalize_usage(response.usage, provider=provider)
                    usage = norm_usage or response.usage

                    billable = usage_billable_tokens(
                        prompt_tokens=usage.prompt_tokens,
                        completion_tokens=usage.completion_tokens,
                        total_tokens=usage.total_tokens,
                        cached_tokens=usage.cached_tokens,
                    )
                    self._total_tokens += billable
                    record_usage_in_diagnostics(
                        self.diagnostics,
                        prompt_tokens=usage.prompt_tokens,
                        completion_tokens=usage.completion_tokens,
                        total_tokens=usage.total_tokens,
                        cached_tokens=usage.cached_tokens,
                    )

                if response.tool_calls:
                    batch_stats = self._process_tool_calls(response)
                    if getattr(batch_stats, "waiting_confirmation_message", None):
                        final_text = batch_stats.waiting_confirmation_message
                        status = LoopStatus.WAITING_CONFIRMATION
                        transition = LoopTransitionReason.WAITING_CONFIRMATION
                        self.diagnostics["two_phase_confirm"] = True
                        break
                    stuck_msg = None
                    try:
                        from butler.core.loop_stuck import guardrail_stuck_message

                        stuck_msg = guardrail_stuck_message(self._guardrails)
                    except Exception as exc:
                        logger.warning("Stuck message check skipped: %s", exc)
                    if stuck_msg:
                        final_text = stuck_msg
                        status = LoopStatus.STUCK
                        transition = LoopTransitionReason.STUCK
                        self.diagnostics["loop_stuck"] = True
                        break
                    if getattr(batch_stats, "clarification_question", None):
                        final_text = batch_stats.clarification_question
                        status = LoopStatus.COMPLETED
                        transition = LoopTransitionReason.SHOULD_CONTINUE_FALSE
                        self.diagnostics["ask_clarification"] = True
                        break
                    if self.callbacks.should_continue:
                        if not self.callbacks.should_continue(iteration, response):
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
                    and self._truncation_retries < self.config.max_truncation_continues
                ):
                    self._truncation_retries += 1
                    if final_text:
                        msg = {"role": "assistant", "content": final_text}
                        from butler.transport.reasoning_replay import store_reasoning_on_message

                        store_reasoning_on_message(msg, final_reasoning)
                        self._messages.append(msg)
                    self._messages.append({"role": "user", "content": truncation_continue_message()})
                    final_text = None
                    transition = LoopTransitionReason.TRUNCATION_CONTINUE
                    continue

                stop_blocked = self._maybe_stop_hook_continue(
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
                        self._total_tokens,
                        max_continuations=max_cont,
                        min_delta_tokens=min_delta,
                    ):
                        if final_text:
                            msg = {"role": "assistant", "content": final_text}
                            from butler.transport.reasoning_replay import store_reasoning_on_message

                            store_reasoning_on_message(msg, final_reasoning)
                            self._messages.append(msg)
                        budget_state.record_continuation(self._total_tokens)
                        nudge = get_budget_continuation_message(
                            budget_state.budget_tokens,
                            attempt=budget_state.continuations_used,
                        )
                        self._messages.append({"role": "user", "content": nudge})
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
                self._messages.append(msg)
                try:
                    from butler.core.session_transcript import record_assistant_message

                    record_assistant_message(
                        steer_session,
                        final_text,
                        tool_calls=self._tool_calls_count,
                    )
                except Exception as exc:
                    logger.debug("Assistant transcript record skipped: %s", exc, exc_info=True)

        finally:
            self.config = original_config
            self._restore_primary_client()
            self._turn_tools = None
            set_parent_callbacks(None)
            if run_callbacks is not None:
                self.callbacks = saved_callbacks

        elapsed = time.time() - start_time
        self.diagnostics["loop_transition_reason"] = transition.value
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
            messages=list(self._messages),
            iterations=iteration,
            total_tokens=self._total_tokens,
            tool_calls_made=self._tool_calls_count,
            elapsed_seconds=elapsed,
            diagnostics=dict(self.diagnostics),
        )
        if self.diagnostics.get("stop_hook_context"):
            logger.debug("Stop hook context already present, skipping post-run hooks")
        elif status == LoopStatus.COMPLETED:
            try:
                from butler.hooks.runner import run_stop_hooks

                stop_hooks = run_stop_hooks(
                    status=status.value,
                    last_assistant_message=final_text or "",
                    session_key=steer_session,
                    iterations=iteration,
                    tool_calls=self._tool_calls_count,
                    elapsed_seconds=elapsed,
                )
                if stop_hooks.additional_context:
                    self.diagnostics["stop_hook_context"] = list(
                        stop_hooks.additional_context
                    )
            except Exception as exc:
                logger.debug("Stop hooks context skipped: %s", exc, exc_info=True)
        return result

    def _maybe_stop_hook_continue(
        self,
        *,
        steer_session: str,
        iteration: int,
        start_time: float,
        final_text: str,
    ) -> bool:
        """Run Stop hooks inside the loop; return True if continuation was injected."""
        try:
            from butler.hooks.runner import run_stop_hooks

            stop_hooks = run_stop_hooks(
                status=LoopStatus.RUNNING.value,
                last_assistant_message=final_text,
                session_key=steer_session,
                iterations=iteration,
                tool_calls=self._tool_calls_count,
                elapsed_seconds=time.time() - start_time,
            )
        except Exception as exc:
            logger.debug("Stop hooks skipped: %s", exc, exc_info=True)
            return False

        if stop_hooks.additional_context:
            self.diagnostics["stop_hook_context"] = list(stop_hooks.additional_context)

        if not stop_hooks.blocked:
            return False

        self.diagnostics["stop_hook_blocked"] = True
        block_msg = (stop_hooks.block_message or "Stop hook 要求继续处理").strip()
        if final_text:
            msg = {"role": "assistant", "content": final_text}
            self._messages.append(msg)
        self._messages.append({
            "role": "user",
            "content": f"[stop-hook-block]\n{block_msg}",
        })
        return True

    def _restore_primary_client(self) -> None:
        if self._primary_client is not None:
            self.client = self._primary_client
            self._fallback_index = 0

    def _estimate_tokens(self, messages: list[dict]) -> int:
        return self._context.estimate_tokens(messages)

    def _compress_context(
        self,
        messages: list[dict],
        *,
        threshold_ratio: float = 0.5,
        min_messages_to_compress: int = 12,
        head_count: int = 3,
        max_tail_messages: int = 12,
        min_tail_messages: int = 4,
        overflow_replay: bool = False,
        diagnostics: dict[str, Any] | None = None,
        initial_injection: Any = None,
    ) -> list[dict]:
        del initial_injection  # explicit compaction turn resolves injection via diagnostics
        return self._context.compress_context(
            messages,
            threshold_ratio=threshold_ratio,
            min_messages_to_compress=min_messages_to_compress,
            head_count=head_count,
            max_tail_messages=max_tail_messages,
            min_tail_messages=min_tail_messages,
            overflow_replay=overflow_replay,
            diagnostics=diagnostics,
        )

    def hygiene_compress_if_needed(
        self,
        *,
        threshold_ratio: float = 0.85,
        hard_message_limit: int = 400,
        max_output_tokens: int | None = None,
    ) -> bool:
        """Preflight compression for long-lived gateway sessions."""
        compressed, messages = self._context.hygiene_compress_if_needed(
            self._messages,
            self.diagnostics,
            threshold_ratio=threshold_ratio,
            hard_message_limit=hard_message_limit,
            max_output_tokens=max_output_tokens,
        )
        if compressed:
            self._messages[:] = messages
        return compressed

    def _prepare_messages_for_api(self) -> list[dict]:
        if self._turn_ephemeral_system:
            self.diagnostics["ephemeral_system"] = self._turn_ephemeral_system
        prepared = self._context.prepare_messages_for_api(
            self._messages,
            pre_llm_transform=self.callbacks.pre_llm_transform,
            diagnostics=self.diagnostics,
        )
        return self._plugins.before_model(prepared)

    def _try_activate_fallback(self) -> bool:
        if not self._fallback_chain:
            return False
        from butler.transport.provider_health import is_circuit_open, record_provider_failure

        try:
            record_provider_failure(
                getattr(self.client, "provider", "") or "",
                getattr(self.client, "model", "") or "",
            )
        except Exception as exc:
            logger.warning("Provider failure recording skipped: %s", exc)
        while self._fallback_index < len(self._fallback_chain) - 1:
            self._fallback_index += 1
            entry = self._fallback_chain[self._fallback_index]
            if is_circuit_open(entry.provider, entry.model):
                continue
            self.client = create_client_from_entry(entry)
            logger.info("Fallback activated: %s/%s", entry.provider, entry.model)
            if self.callbacks.on_fallback:
                self.callbacks.on_fallback(entry.provider, entry.model)
            return True
        return False

    def _interrupt_check(self) -> bool:
        return bool(
            self._interrupted
            or (self._thread_id is not None and is_interrupted(self._thread_id))
        )

    def _call_llm_with_retry(self) -> Optional[NormalizedResponse]:
        empty_retries = [self._empty_retries]
        from butler.core.streaming_tools import streaming_tools_enabled

        on_tool_ready = None
        if streaming_tools_enabled() and self.config.stream:
            prefetch = self._tool_prefetch

            def on_tool_ready(_idx: int, tool_id: str, name: str, args: dict) -> None:
                if self._interrupt_check():
                    return
                key = tool_id or f"call_{_idx}"
                if key in prefetch:
                    return
                if self._guardrails:
                    from butler.tool_guardrails import synthetic_result

                    before = self._guardrails.before_call(name, args)
                    if before.action == "ask" and before.code == "doom_loop":
                        blocked = _doom_loop_block_on_ask(before, name, args)
                        if blocked is not None:
                            prefetch[key] = blocked
                            return
                    if before.should_halt:
                        prefetch[key] = synthetic_result(before)
                        return
                prefetch[key] = self._dispatch_tool(name, args)

        response, interrupted = call_llm_with_retry(
            client=self.client,
            config=self.config,
            callbacks=self.callbacks,
            tools=self._turn_tools if self._turn_tools is not None else self.tools,
            messages=self._messages,
            diagnostics=self.diagnostics,
            prepare_messages=self._prepare_messages_for_api,
            compress_messages=self._compress_context,
            interrupt_check=self._interrupt_check,
            try_activate_fallback=self._try_activate_fallback,
            empty_retries=empty_retries,
            on_tool_call_ready=on_tool_ready,
        )
        self._empty_retries = empty_retries[0]
        if interrupted:
            self._interrupted = True
        return response

    def _process_tool_calls(self, response: NormalizedResponse):
        stats = process_tool_calls(
            response=response,
            messages=self._messages,
            config=self.config,
            callbacks=self.callbacks,
            guardrails=self._guardrails,
            dispatch_tool=self._dispatch_tool,
            interrupt_check=self._interrupt_check,
            prefetched=self._tool_prefetch,
        )
        self._tool_prefetch.clear()
        self._tool_calls_count += stats.tools_started
        try:
            self._messages[:] = self._plugins.after_tools(
                self._messages,
                tool_stats=stats,
            )
        except Exception as exc:
            logger.warning("after_tools middleware skipped: %s", exc)
        if self._guardrails is not None:
            try:
                counts = getattr(self._guardrails, "_same_tool_failure_counts", {}) or {}
                if counts:
                    worst_tool, worst_n = max(counts.items(), key=lambda kv: kv[1])
                    from butler.core.reflexion_ephemeral import maybe_apply_reflexion

                    maybe_apply_reflexion(
                        self.diagnostics,
                        tool_name=worst_tool,
                        failure_count=int(worst_n),
                    )
            except Exception as exc:
                logger.debug("Reflexion apply skipped: %s", exc, exc_info=True)
        return stats

    def _dispatch_tool(self, name: str, args: dict) -> str:
        def _inner(n: str, a: dict) -> str:
            return dispatch_tool_with_envelope(self.tool_dispatcher, n, a)

        return self._plugins.wrap_tool_call(name, args, _inner)

    @property
    def messages(self) -> list[dict]:
        return list(self._messages)

    @messages.setter
    def messages(self, value: list[dict]) -> None:
        self._messages = list(value)

    def reset(self) -> None:
        self._messages.clear()
        self._total_tokens = 0
        self._tool_calls_count = 0
        self._interrupted = False
        self._empty_retries = 0
        self._truncation_retries = 0
        self._turn_tools = None
        self._turn_ephemeral_system = None
        self._fallback_index = 0
        self._primary_client = None
        self._tool_prefetch.clear()
        self.diagnostics.clear()
        if self._context is not None:
            self._context.compression_summary = ""
            self._context.consecutive_compact_failures = 0
        from butler.core.tool_call_limits import reset_tool_call_limiter_for_turn

        reset_tool_call_limiter_for_turn()

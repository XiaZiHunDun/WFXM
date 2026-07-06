"""Butler Agent Loop — the core LLM conversation engine."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Optional, cast
from contextlib import AbstractContextManager
from collections.abc import Iterator

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
from butler.core.tool_batch import (
    ToolBatchStats,
    dispatch_tool_with_envelope,
    process_tool_calls,
)
from butler.tool_guardrails import ToolCallGuardrailController
from butler.core.interrupt import clear_interrupt, is_interrupted, set_interrupt
from butler.core.steer import clear_steer, mark_run_active, mark_run_inactive
from butler.transport.base import LLMClientProtocol
from butler.transport.fallback import FallbackEntry, create_client_from_entry
from butler.transport.llm_client import LLMClient
from butler.transport.types import NormalizedResponse

# R1-8 split: phase helpers extracted from _run_turn_body (337L → 4 phase
# orchestrators + 2 user-message sub-phases) live in this sibling module.
# The host class imports them and delegates per-iteration work.
from butler.core.agent_loop_phases import (  # noqa: E402 — split import
    TurnBodyState,
    _mark_interrupted_status,
    _phase_call_llm,
    _phase_dispatch_tools,
    _phase_finalize,
    _phase_init,
    _phase_resolve_user_text,
    _phase_enrich_user_text,
)

from butler.core.agent_loop_ops import (
    apply_reflexion_safe,
    doom_loop_block_on_ask,
    emit_skipped_plugin_metric,
    filter_fallback_chain_safe,
    maybe_compact_turn_safe,
    record_provider_failure_safe,
    refresh_model_binding_safe,
    run_after_tools_plugins_safe,
    run_stop_hooks_safe,
)

logger = logging.getLogger(__name__)

# Audit R2-9: cap on the per-session diagnostics["skipped"] list and truncation
# length for the error string. Both are the empirical "good enough" defaults —
# the cap keeps the list bounded for long sessions, the truncation keeps the
# payload under the typical MCP/JSON envelope limit.
_MAX_SKIPPED_PLUGIN_ENTRIES = 50
_MAX_SKIPPED_PLUGIN_ERROR_LEN = 200


class AgentLoop:
    """Self-contained LLM conversation loop with tool calling."""

    def __init__(
        self,
        client: LLMClientProtocol,
        *,
        system_prompt: str = "",
        tools: Optional[list[dict[str, Any]]] = None,
        tool_dispatcher: Optional[Callable[[str, dict[str, Any]], str]] = None,
        config: Optional[LoopConfig] = None,
        callbacks: Optional[LoopCallbacks] = None,
    ):
        self.client: LLMClientProtocol = client
        self.system_prompt = system_prompt
        self.tools = tools or []
        self.tool_dispatcher = tool_dispatcher
        self.config = config or LoopConfig()
        self.callbacks = callbacks or LoopCallbacks()

        self._messages: list[dict[str, Any]] = []
        self._turn_tools: list[dict[str, Any]] | None = None
        self._interrupted = False
        self._total_tokens = 0
        self._tool_calls_count = 0
        self._guardrails = ToolCallGuardrailController() if self.config.enable_guardrails else None
        self._context = ContextPipeline(self.config)
        self._context.attach_loop(self)
        self._turn_ephemeral_system: str | None = None
        self._thread_id: int | None = None
        self.diagnostics: dict[str, Any] = {}
        _chain = list(self.config.fallback_entries or [])
        _chain = filter_fallback_chain_safe(_chain)
        self._fallback_chain: list[FallbackEntry] = _chain
        self._fallback_index = 0
        self._primary_client: LLMClient | None = None
        self._empty_retries = 0
        self._truncation_retries = 0
        self._tool_prefetch: dict[str, str] = {}
        self._orchestrator: Any | None = None
        self._session_key: str = ""
        from butler.core.loop_plugins import default_plugin_registry

        self._plugins = default_plugin_registry(self.config)

    def bind_execution(
        self,
        orchestrator: Any | None = None,
        *,
        session_key: str = "",
    ) -> None:
        """Bind orchestrator/session for tool dispatch when contextvars are missing."""
        if orchestrator is not None:
            self._orchestrator = orchestrator
        self._session_key = str(session_key or self._session_key or "")

    def _tool_execution_context(self) -> AbstractContextManager[None]:
        from contextlib import contextmanager

        from butler.execution_context import (
            get_current_orchestrator,
            get_current_session_key,
            use_execution_context,
        )

        @contextmanager
        def _ctx() -> Iterator[None]:
            orch = get_current_orchestrator() or self._orchestrator
            sk = str(get_current_session_key() or self._session_key or "")
            if orch is None and not sk:
                yield
                return
            with use_execution_context(orch, session_key=sk):
                yield

        return _ctx()

    @property
    def _compression_summary(self) -> str:
        return str(self._context.compression_summary)

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

    def _record_skipped_plugin(self, plugin_name: str, exc: BaseException) -> None:
        """Record a skipped plugin/middleware to ``diagnostics['skipped']``.

        Replaces the old per-site ``logger.debug(..., exc_info=True)`` and
        ``logger.warning(...)`` calls scattered through agent_loop.py. Each
        skip now logs at ERROR with a full traceback AND appends a structured
        entry to ``self.diagnostics`` so the failure is visible to ``/诊断``.

        The list is capped at ``_MAX_SKIPPED_PLUGIN_ENTRIES`` to prevent
        unbounded growth across long-lived sessions; older entries are dropped
        first (FIFO). Error strings are truncated to
        ``_MAX_SKIPPED_PLUGIN_ERROR_LEN`` to keep the payload small.
        """
        from butler.core.best_effort import record_best_effort_skip

        label = f"agent_loop.{plugin_name}"
        logger.error("%s skipped: %s", plugin_name, exc, exc_info=exc)
        record_best_effort_skip(label, exc)
        emit_skipped_plugin_metric(label)
        bucket = self.diagnostics.setdefault("skipped", [])
        bucket.append({
            "plugin": plugin_name,
            "error": str(exc)[:_MAX_SKIPPED_PLUGIN_ERROR_LEN],
            "type": type(exc).__name__,
        })
        if len(bucket) > _MAX_SKIPPED_PLUGIN_ENTRIES:
            del bucket[: len(bucket) - _MAX_SKIPPED_PLUGIN_ENTRIES]

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
                from butler.mcp.turn_scrape_dedup import turn_scrape_dedup_scope
                from butler.tools.network_search_policy import turn_network_search_scope

                with turn_network_search_scope(user_message):
                    with turn_scrape_dedup_scope():
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
    ) -> tuple[str, list[dict[str, Any]]]:
        """Sanitize user input, select tools, record transcript.

        R1-8: thin orchestrator that delegates to two sub-phases —
        ``_phase_resolve_user_text`` (sanitize + reminder + append) and
        ``_phase_enrich_user_text`` (tool selection + transcript record).
        Each sub-phase lives in :mod:`butler.core.agent_loop_phases` and
        is a thin orchestrator under 50 source lines.

        Returns ``(user_content, turn_tools)``.
        """
        user_content = _phase_resolve_user_text(self, user_message)
        turn_tools = _phase_enrich_user_text(self, user_content, steer_session)
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
        # R1-8 split: 4 audit-named phases (init / call_llm / dispatch_tools
        # / finalize) are thin orchestrators in agent_loop_phases. This
        # method is reduced to a while loop that calls them in order.
        state = TurnBodyState()
        _phase_init(self, user_message, steer_session, state)
        try:
            while (
                state.status == LoopStatus.RUNNING
                and state.iteration < self.config.max_iterations
            ):
                if self._interrupt_check():
                    _mark_interrupted_status(state)
                    break
                state.iteration += 1
                from butler.core.delegate_context import set_parent_messages

                set_parent_messages(self._messages)
                if maybe_compact_turn_safe(self, state):
                    continue
                response = _phase_call_llm(self, state)
                if response is None:
                    break
                if not _phase_dispatch_tools(
                    self, response, state, start_time, steer_session,
                ):
                    break
        finally:
            self.config = state.original_config
            self._restore_primary_client()
            self._turn_tools = None
            set_parent_callbacks(None)
            if run_callbacks is not None:
                self.callbacks = saved_callbacks
        return _phase_finalize(self, state, run_callbacks, steer_session, start_time)
    def _maybe_stop_hook_continue(
        self,
        *,
        steer_session: str,
        iteration: int,
        start_time: float,
        final_text: str,
    ) -> bool:
        """Run Stop hooks inside the loop; return True if continuation was injected."""
        stop_hooks = run_stop_hooks_safe(
            self,
            steer_session=steer_session,
            iteration=iteration,
            start_time=start_time,
            final_text=final_text,
        )
        if stop_hooks is None:
            return False

        if stop_hooks.additional_context:
            from butler.core.hook_context_adapter import (
                adapt_hook_context_lines,
                apply_hook_context_to_diagnostics,
                to_hook_context_view,
            )

            adapted = adapt_hook_context_lines(
                stop_hooks.additional_context,
                source="stop_hook",
            )
            if adapted:
                self.diagnostics["stop_hook_context"] = adapted
                view = to_hook_context_view(adapted, source="stop_hook_merged")
                apply_hook_context_to_diagnostics(view, self.diagnostics)

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

    def _estimate_tokens(self, messages: list[dict[str, Any]]) -> int:
        return int(self._context.estimate_tokens(messages))

    def _compress_context(
        self,
        messages: list[dict[str, Any]],
        *,
        threshold_ratio: float = 0.5,
        min_messages_to_compress: int = 12,
        head_count: int = 3,
        max_tail_messages: int = 12,
        min_tail_messages: int = 4,
        overflow_replay: bool = False,
        diagnostics: dict[str, Any] | None = None,
        initial_injection: Any = None,
    ) -> list[dict[str, Any]]:
        del initial_injection  # explicit compaction turn resolves injection via diagnostics
        return cast(
            list[dict[str, Any]],
            self._context.compress_context(
                messages,
                threshold_ratio=threshold_ratio,
                min_messages_to_compress=min_messages_to_compress,
                head_count=head_count,
                max_tail_messages=max_tail_messages,
                min_tail_messages=min_tail_messages,
                overflow_replay=overflow_replay,
                diagnostics=diagnostics,
            ),
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
        return bool(compressed)

    def _prepare_messages_for_api(self) -> list[dict[str, Any]]:
        if self._turn_ephemeral_system:
            self.diagnostics["ephemeral_system"] = self._turn_ephemeral_system
        prepared = self._context.prepare_messages_for_api(
            self._messages,
            pre_llm_transform=self.callbacks.pre_llm_transform,
            diagnostics=self.diagnostics,
        )
        return cast(list[dict[str, Any]], self._plugins.before_model(prepared))

    def _try_activate_fallback(self) -> bool:
        from butler.transport.provider_health import is_circuit_open

        if not self._fallback_chain:
            return False

        record_provider_failure_safe(self)
        while self._fallback_index < len(self._fallback_chain) - 1:
            self._fallback_index += 1
            entry = self._fallback_chain[self._fallback_index]
            if is_circuit_open(entry.provider, entry.model):
                continue
            self.client = create_client_from_entry(entry)
            logger.info("Fallback activated: %s/%s", entry.provider, entry.model)
            refresh_model_binding_safe(self)
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

            def on_tool_ready(_idx: int, tool_id: str, name: str, args: dict[str, Any]) -> None:
                if self._interrupt_check():
                    return
                key = tool_id or f"call_{_idx}"
                if key in prefetch:
                    return
                if self._guardrails:
                    from butler.tool_guardrails import synthetic_result

                    before = self._guardrails.before_call(name, args)
                    if before.action == "ask" and before.code == "doom_loop":
                        blocked = doom_loop_block_on_ask(before, name, args)
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

    def _process_tool_calls(self, response: NormalizedResponse) -> ToolBatchStats:
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
        if response.tool_calls:
            used = self.diagnostics.setdefault("tools_used", [])
            for tc in response.tool_calls:
                name = getattr(tc, "name", "") or ""
                if name and name not in used:
                    used.append(name)
        run_after_tools_plugins_safe(self, stats)
        apply_reflexion_safe(self)
        return stats

    def _dispatch_tool(self, name: str, args: dict[str, Any]) -> str:
        def _inner(n: str, a: dict[str, Any]) -> str:
            return cast(str, dispatch_tool_with_envelope(self.tool_dispatcher, n, a))

        with self._tool_execution_context():
            return cast(str, self._plugins.wrap_tool_call(name, args, _inner))

    @property
    def messages(self) -> list[dict[str, Any]]:
        return list(self._messages)

    @messages.setter
    def messages(self, value: list[dict[str, Any]]) -> None:
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

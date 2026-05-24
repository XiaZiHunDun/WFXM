"""Butler Agent Loop — the core LLM conversation engine."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, List, Optional

from butler.core.context_pipeline import ContextPipeline
from butler.core.delegate_context import set_parent_callbacks
from butler.core.llm_retry import call_llm_with_retry
from butler.core.loop_response import (
    needs_truncation_continue,
    truncation_continue_message,
)
from butler.core.loop_types import LoopCallbacks, LoopConfig, LoopResult, LoopStatus
from butler.core.message_sanitize import sanitize_surrogates
from butler.core.tool_batch import dispatch_tool_with_envelope, process_tool_calls
from butler.tool_guardrails import ToolCallGuardrailController
from butler.tools.interrupt import clear_interrupt, is_interrupted, set_interrupt
from butler.core.steer import clear_steer, mark_run_active, mark_run_inactive
from butler.transport.fallback import FallbackEntry, create_client_from_entry
from butler.transport.llm_client import LLMClient
from butler.transport.types import NormalizedResponse

logger = logging.getLogger(__name__)


class AgentLoop:
    """Self-contained LLM conversation loop with tool calling."""

    def __init__(
        self,
        client: LLMClient,
        *,
        system_prompt: str = "",
        tools: Optional[list[dict]] = None,
        tool_dispatcher: Optional[Callable[[str, dict], str]] = None,
        config: Optional[LoopConfig] = None,
        callbacks: Optional[LoopCallbacks] = None,
    ):
        self.client = client
        self.system_prompt = system_prompt
        self.tools = tools or []
        self.tool_dispatcher = tool_dispatcher
        self.config = config or LoopConfig()
        self.callbacks = callbacks or LoopCallbacks()

        self._messages: list[dict] = []
        self._interrupted = False
        self._total_tokens = 0
        self._tool_calls_count = 0
        self._guardrails = ToolCallGuardrailController() if self.config.enable_guardrails else None
        self._context = ContextPipeline(self.config)
        self._thread_id: int | None = None
        self._fallback_chain: list[FallbackEntry] = list(self.config.fallback_entries or [])
        self._fallback_index = 0
        self._primary_client: LLMClient | None = None
        self._empty_retries = 0
        self._truncation_retries = 0
        self.diagnostics: dict[str, Any] = {}

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
    ) -> LoopResult:
        start_time = time.time()
        saved_callbacks = self.callbacks
        if run_callbacks is not None:
            from butler.gateway.outbound_bridge import merge_loop_callbacks

            self.callbacks = merge_loop_callbacks(saved_callbacks, run_callbacks)
        pre_run_diagnostics = {
            k: v for k, v in self.diagnostics.items()
            if str(k).startswith("hygiene_")
        }
        self.diagnostics = dict(pre_run_diagnostics)
        self._interrupted = False
        self._thread_id = threading.get_ident() if hasattr(threading, "get_ident") else None
        clear_interrupt(self._thread_id)
        from butler.execution_context import get_current_session_key

        _steer_session = get_current_session_key() or "default"
        mark_run_active(_steer_session)
        try:
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
        clear_steer(steer_session)
        self._primary_client = self.client
        self._fallback_index = 0
        self._empty_retries = 0
        self._truncation_retries = 0
        set_parent_callbacks(self.callbacks)
        if self._guardrails:
            self._guardrails.reset_for_turn()

        if not self._messages:
            if self.system_prompt:
                self._messages.append({"role": "system", "content": self.system_prompt})

        self._messages.append({"role": "user", "content": sanitize_surrogates(user_message)})

        final_text = None
        final_reasoning = None
        status = LoopStatus.RUNNING
        iteration = 0

        try:
            while status == LoopStatus.RUNNING and iteration < self.config.max_iterations:
                if self._interrupted or (self._thread_id and is_interrupted(self._thread_id)):
                    status = LoopStatus.INTERRUPTED
                    break

                iteration += 1
                if iteration > 1 and self.callbacks.on_stream_boundary:
                    self.callbacks.on_stream_boundary()
                if self.callbacks.on_iteration:
                    self.callbacks.on_iteration(iteration, status)

                response = self._call_llm_with_retry()
                if response is None:
                    status = LoopStatus.INTERRUPTED if self._interrupted else LoopStatus.ERROR
                    break

                if response.usage:
                    self._total_tokens += response.usage.total_tokens

                if response.tool_calls:
                    self._process_tool_calls(response)
                    if self.callbacks.should_continue:
                        if not self.callbacks.should_continue(iteration, response):
                            final_text = response.content
                            status = LoopStatus.COMPLETED
                            break
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
                    continue
                status = LoopStatus.COMPLETED

            if status == LoopStatus.RUNNING:
                status = LoopStatus.TOOL_LIMIT

            if final_text:
                msg = {"role": "assistant", "content": final_text}
                from butler.transport.reasoning_replay import store_reasoning_on_message

                store_reasoning_on_message(msg, final_reasoning)
                self._messages.append(msg)

        finally:
            self._restore_primary_client()
            set_parent_callbacks(None)
            if run_callbacks is not None:
                self.callbacks = saved_callbacks

        elapsed = time.time() - start_time
        result = LoopResult(
            status=status,
            final_response=final_text,
            reasoning=final_reasoning,
            messages=list(self._messages),
            iterations=iteration,
            total_tokens=self._total_tokens,
            tool_calls_made=self._tool_calls_count,
            elapsed_seconds=elapsed,
            diagnostics=dict(self.diagnostics),
        )
        try:
            from butler.hooks.runner import run_stop_hooks

            run_stop_hooks(
                status=status.value,
                last_assistant_message=final_text or "",
                session_key=steer_session,
                iterations=iteration,
                tool_calls=self._tool_calls_count,
                elapsed_seconds=elapsed,
            )
        except Exception as exc:
            logger.debug("Stop hooks skipped: %s", exc)
        return result

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
    ) -> list[dict]:
        return self._context.compress_context(
            messages,
            threshold_ratio=threshold_ratio,
            min_messages_to_compress=min_messages_to_compress,
            head_count=head_count,
            max_tail_messages=max_tail_messages,
            min_tail_messages=min_tail_messages,
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
        return self._context.prepare_messages_for_api(
            self._messages,
            pre_llm_transform=self.callbacks.pre_llm_transform,
        )

    def _try_activate_fallback(self) -> bool:
        if not self._fallback_chain or self._fallback_index >= len(self._fallback_chain) - 1:
            return False
        self._fallback_index += 1
        entry = self._fallback_chain[self._fallback_index]
        self.client = create_client_from_entry(entry)
        logger.info("Fallback activated: %s/%s", entry.provider, entry.model)
        if self.callbacks.on_fallback:
            self.callbacks.on_fallback(entry.provider, entry.model)
        return True

    def _interrupt_check(self) -> bool:
        return bool(
            self._interrupted
            or (self._thread_id is not None and is_interrupted(self._thread_id))
        )

    def _call_llm_with_retry(self) -> Optional[NormalizedResponse]:
        empty_retries = [self._empty_retries]
        response, interrupted = call_llm_with_retry(
            client=self.client,
            config=self.config,
            callbacks=self.callbacks,
            tools=self.tools,
            messages=self._messages,
            diagnostics=self.diagnostics,
            prepare_messages=self._prepare_messages_for_api,
            compress_messages=self._compress_context,
            interrupt_check=self._interrupt_check,
            try_activate_fallback=self._try_activate_fallback,
            empty_retries=empty_retries,
        )
        self._empty_retries = empty_retries[0]
        if interrupted:
            self._interrupted = True
        return response

    def _process_tool_calls(self, response: NormalizedResponse) -> None:
        stats = process_tool_calls(
            response=response,
            messages=self._messages,
            config=self.config,
            callbacks=self.callbacks,
            guardrails=self._guardrails,
            dispatch_tool=self._dispatch_tool,
            interrupt_check=self._interrupt_check,
        )
        self._tool_calls_count += stats.tools_started

    def _dispatch_tool(self, name: str, args: dict) -> str:
        return dispatch_tool_with_envelope(self.tool_dispatcher, name, args)

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

"""Butler Agent Loop — the core LLM conversation engine."""

from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from typing import Any, Callable, Dict, List, Optional

from butler.core.context_compressor import _estimate_tokens, compress_messages
from butler.core.delegate_context import child_callbacks, set_parent_callbacks
from butler.core.loop_response import (
    empty_retry_message,
    needs_empty_content_retry,
    needs_truncation_continue,
    sanitize_response,
    truncation_continue_message,
)
from butler.core.loop_types import LoopCallbacks, LoopConfig, LoopResult, LoopStatus
from butler.core.hygiene_preflight import run_hygiene_preflight
from butler.core.message_repair import repair_message_sequence, repair_tool_arguments
from butler.core.message_sanitize import (
    drop_thinking_only_assistants,
    sanitize_api_messages,
    sanitize_surrogates,
)
from butler.core.parallel_tools import execute_tools_parallel
from butler.core.retry_policy import retry_delay_for_config
from butler.core.schema_recovery import recover_schema_after_error
from butler.core.steer import apply_steer_to_tool_results, clear_steer
from butler.tool_guardrails import (
    ToolCallGuardrailController,
    append_guidance,
    synthetic_result,
)
from butler.tools.interrupt import clear_interrupt, is_interrupted, set_interrupt
from butler.transport.error_classifier import classify_api_error
from butler.transport.fallback import FallbackEntry, build_fallback_chain, create_client_from_entry
from butler.transport.interruptible_client import StaleApiCallError
from butler.transport.llm_client import LLMClient
from butler.transport.types import NormalizedResponse, ToolCall

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
        self._compression_summary = ""
        self._thread_id: int | None = None
        self._fallback_chain: list[FallbackEntry] = list(self.config.fallback_entries or [])
        self._fallback_index = 0
        self._primary_client: LLMClient | None = None
        self._empty_retries = 0
        self._truncation_retries = 0
        self.diagnostics: dict[str, Any] = {}

    def interrupt(self) -> None:
        self._interrupted = True
        if self._thread_id is not None:
            set_interrupt(True, self._thread_id)

    def clear_interrupt(self) -> None:
        self._interrupted = False
        if self._thread_id is not None:
            clear_interrupt(self._thread_id)

    def run(self, user_message: str) -> LoopResult:
        start_time = time.time()
        pre_run_diagnostics = {
            k: v for k, v in self.diagnostics.items()
            if str(k).startswith("hygiene_")
        }
        self.diagnostics = dict(pre_run_diagnostics)
        self._interrupted = False
        self._thread_id = threading.get_ident() if hasattr(threading, "get_ident") else None
        clear_interrupt(self._thread_id)
        clear_steer()
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

        elapsed = time.time() - start_time
        return LoopResult(
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

    def _restore_primary_client(self) -> None:
        if self._primary_client is not None:
            self.client = self._primary_client
            self._fallback_index = 0

    def _estimate_tokens(self, messages: list[dict]) -> int:
        return _estimate_tokens(messages)

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
        compressed, summary, did = compress_messages(
            messages,
            max_tokens=self.config.max_context_tokens,
            threshold_ratio=threshold_ratio,
            previous_summary=self._compression_summary,
            min_messages_to_compress=min_messages_to_compress,
            head_count=head_count,
            max_tail_messages=max_tail_messages,
            min_tail_messages=min_tail_messages,
        )
        if did and summary:
            self._compression_summary = summary
        return compressed

    def hygiene_compress_if_needed(
        self,
        *,
        threshold_ratio: float = 0.85,
        hard_message_limit: int = 400,
    ) -> bool:
        """Preflight compression for long-lived gateway sessions."""
        messages = list(self._messages)
        result = run_hygiene_preflight(
            messages,
            max_context_tokens=self.config.max_context_tokens,
            diagnostics=self.diagnostics,
            estimate_tokens=self._estimate_tokens,
            compress=self._compress_context,
            threshold_ratio=threshold_ratio,
            hard_message_limit=hard_message_limit,
        )
        if not result.compressed:
            return False

        self._messages[:] = result.messages
        logger.info(
            "Gateway hygiene compressed %d->%d messages (~%d tokens, threshold=%d)",
            len(messages),
            len(result.messages),
            self.diagnostics.get("hygiene_estimated_tokens", 0),
            self.diagnostics.get("hygiene_threshold_tokens", 0),
        )
        return True

    def _prepare_messages_for_api(self) -> list[dict]:
        messages = self._compress_context(list(self._messages))
        messages, _ = repair_message_sequence(messages)
        repair_tool_arguments(messages)
        messages, _ = sanitize_api_messages(messages)
        messages, _ = drop_thinking_only_assistants(messages)
        if self.callbacks.pre_llm_transform:
            messages = self.callbacks.pre_llm_transform(messages)
        return messages

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
        messages_to_send = self._prepare_messages_for_api()
        if self.callbacks.on_llm_start:
            self.callbacks.on_llm_start(messages_to_send)

        last_error: Exception | None = None
        compress_attempted = False
        schema_recovery_attempted = False
        tools_to_send = self.tools if self.tools else None

        for attempt in range(self.config.max_retries):
            if self._interrupt_check():
                return None

            try:
                common = {
                    "messages": messages_to_send,
                    "tools": tools_to_send,
                    "check_interrupt": self._interrupt_check,
                    "stale_timeout": self.config.api_stale_timeout,
                }
                if self.config.stream and self.callbacks.on_stream_delta:
                    response = self.client.stream(
                        on_delta=self.callbacks.on_stream_delta,
                        **common,
                    )
                else:
                    response = self.client.complete(**common)

                response = sanitize_response(response)

                if (
                    needs_empty_content_retry(response)
                    and self._empty_retries < self.config.max_empty_content_retries
                ):
                    self._empty_retries += 1
                    self._messages.append({"role": "user", "content": empty_retry_message()})
                    messages_to_send = self._prepare_messages_for_api()
                    continue

                if self.callbacks.on_llm_complete:
                    self.callbacks.on_llm_complete(response)
                return response

            except InterruptedError:
                self._interrupted = True
                return None

            except Exception as exc:
                last_error = exc
                classified = classify_api_error(
                    exc,
                    provider=getattr(self.client, "provider_name", ""),
                    model=getattr(self.client, "model", ""),
                )
                logger.warning(
                    "LLM attempt %d/%d failed [%s]: %s",
                    attempt + 1, self.config.max_retries, classified.reason.value, exc,
                )
                if self.callbacks.on_error:
                    self.callbacks.on_error(exc, attempt + 1)

                if isinstance(exc, StaleApiCallError) and classified.retryable:
                    if attempt < self.config.max_retries - 1:
                        time.sleep(self._retry_delay(attempt))
                        continue

                if tools_to_send and not schema_recovery_attempted:
                    recovered = recover_schema_after_error(
                        exc,
                        tools_to_send,
                        diagnostics=self.diagnostics,
                    )
                    schema_recovery_attempted = schema_recovery_attempted or recovered.attempted
                    if recovered.attempted and recovered.tools is not None:
                        tools_to_send = recovered.tools
                    if recovered.recovered:
                        if attempt < self.config.max_retries - 1:
                            logger.info(
                                "Retrying LLM call after stripping %d schema pattern/format keywords",
                                recovered.stripped,
                            )
                            continue

                if classified.should_compress and not compress_attempted:
                    compress_attempted = True
                    self._messages[:] = self._compress_context(list(self._messages))
                    messages_to_send = self._prepare_messages_for_api()
                    continue

                if classified.should_fallback and self._try_activate_fallback():
                    continue

                if not classified.retryable:
                    break

                if attempt < self.config.max_retries - 1:
                    time.sleep(self._retry_delay(attempt))

        logger.error("All LLM attempts failed: %s", last_error)
        return None

    def _retry_delay(self, attempt_index: int) -> float:
        return retry_delay_for_config(self.config, attempt_index)

    def _process_tool_calls(self, response: NormalizedResponse) -> None:
        if not response.tool_calls:
            return

        from butler.transport.reasoning_replay import store_reasoning_on_message

        assistant_msg: dict[str, Any] = {"role": "assistant", "content": response.content}
        store_reasoning_on_message(assistant_msg, response.reasoning)
        tool_call_records = []
        for tc in response.tool_calls:
            tc_id = tc.id or f"call_{uuid.uuid4().hex[:8]}"
            if not tc.id:
                tc.id = tc_id
            tool_call_records.append({
                "id": tc_id,
                "type": "function",
                "function": {"name": tc.name, "arguments": tc.arguments},
            })
        assistant_msg["tool_calls"] = tool_call_records
        self._messages.append(assistant_msg)

        if self._guardrails and self._guardrails.halt_decision:
            return

        def _dispatch_one(name: str, args: dict) -> str:
            if self._guardrails:
                before = self._guardrails.before_call(name, args)
                if before.should_halt:
                    return synthetic_result(before)
            result = self._dispatch_tool(name, args)
            if self._guardrails:
                after = self._guardrails.after_call(name, args, result)
                result = append_guidance(result, after)
                if after.should_halt:
                    self._guardrails._halt_decision = after
            return result

        def _on_start(name: str, args: dict) -> None:
            self._tool_calls_count += 1
            if self.callbacks.on_tool_start:
                self.callbacks.on_tool_start(name, args)

        def _on_complete(name: str, result: str) -> None:
            if self.callbacks.on_tool_complete:
                self.callbacks.on_tool_complete(name, result)

        check = self._interrupt_check

        if self.config.enable_parallel_tools and len(response.tool_calls) > 1:
            pairs = execute_tools_parallel(
                response.tool_calls,
                _dispatch_one,
                on_start=_on_start,
                on_complete=_on_complete,
                check_interrupt=check,
            )
        else:
            pairs = []
            for tc in response.tool_calls:
                if check():
                    break
                try:
                    args = tc.args_dict()
                except Exception:
                    args = {}
                _on_start(tc.name, args)
                result = _dispatch_one(tc.name, args)
                _on_complete(tc.name, result)
                pairs.append((tc, result))

        for tc, result in pairs:
            self._messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result,
            })

        apply_steer_to_tool_results(self._messages, len(pairs))

    def _dispatch_tool(self, name: str, args: dict) -> str:
        if self.tool_dispatcher:
            try:
                return self.tool_dispatcher(name, args)
            except Exception as exc:
                logger.error("Tool %s failed: %s", name, exc)
                return json.dumps({"error": f"Tool execution failed: {exc}"})
        return json.dumps({"error": f"No tool dispatcher configured, cannot run '{name}'"})

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

"""Butler Agent Loop — the core LLM conversation engine.

This is the heart of the Butler system. Unlike importing an external
agent engine, Butler controls every step: message construction,
LLM calls, tool dispatch, error handling, and context management.

Key design principles:
  - Every step is hookable and overridable
  - Tool dispatch goes through Butler's own registry
  - Sub-agent spawning goes through Butler's orchestrator
  - Memory and skills are injected per-turn, not just at init
"""

from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from butler.core.context_compressor import compress_messages
from butler.core.message_repair import repair_message_sequence, repair_tool_arguments
from butler.core.parallel_tools import execute_tools_parallel
from butler.tool_guardrails import (
    ToolCallGuardrailController,
    append_guidance,
    synthetic_result,
)
from butler.tools.interrupt import clear_interrupt, is_interrupted, set_interrupt
from butler.transport.error_classifier import classify_api_error
from butler.transport.fallback import FallbackEntry, build_fallback_chain, create_client_from_entry
from butler.transport.llm_client import LLMClient
from butler.transport.types import NormalizedResponse, ToolCall

logger = logging.getLogger(__name__)


class LoopStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    TOOL_LIMIT = "tool_limit"
    ERROR = "error"
    INTERRUPTED = "interrupted"


@dataclass
class LoopConfig:
    """Configuration for the agent loop."""
    max_iterations: int = 30
    max_retries: int = 3
    retry_delay: float = 1.0
    max_context_tokens: int = 128000
    stream: bool = True
    enable_guardrails: bool = True
    enable_parallel_tools: bool = True
    fallback_entries: list | None = None


@dataclass
class LoopCallbacks:
    """Hooks into every phase of the agent loop."""
    on_llm_start: Optional[Callable[[list[dict]], None]] = None
    on_llm_complete: Optional[Callable[[NormalizedResponse], None]] = None
    on_stream_delta: Optional[Callable[[str], None]] = None
    on_tool_start: Optional[Callable[[str, dict], None]] = None
    on_tool_complete: Optional[Callable[[str, str], None]] = None
    on_error: Optional[Callable[[Exception, int], None]] = None
    on_iteration: Optional[Callable[[int, LoopStatus], None]] = None
    pre_llm_transform: Optional[Callable[[list[dict]], list[dict]]] = None
    should_continue: Optional[Callable[[int, NormalizedResponse], bool]] = None


@dataclass
class LoopResult:
    """Complete result of an agent loop execution."""
    status: LoopStatus
    final_response: Optional[str] = None
    reasoning: Optional[str] = None
    messages: list = field(default_factory=list)
    iterations: int = 0
    total_tokens: int = 0
    tool_calls_made: int = 0
    error: Optional[str] = None
    elapsed_seconds: float = 0.0


class AgentLoop:
    """Self-contained LLM conversation loop with tool calling.

    This is Butler's own agent engine — not a wrapper around any
    external agent. Butler controls the full lifecycle:
      1. Build messages (system + memory + skill + history)
      2. Call LLM (via Transport layer)
      3. Parse response (text / tool_calls / errors)
      4. Dispatch tools (via Butler's tool registry)
      5. Manage context (compression when too long)
      6. Repeat until done
    """

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

    def interrupt(self) -> None:
        self._interrupted = True
        if self._thread_id is not None:
            set_interrupt(True, self._thread_id)

    def clear_interrupt(self) -> None:
        self._interrupted = False
        if self._thread_id is not None:
            clear_interrupt(self._thread_id)

    def run(self, user_message: str) -> LoopResult:
        """Execute a full conversation turn.

        Sends the user message to the LLM, handles tool calls in a
        loop, and returns the final result.
        """
        start_time = time.time()
        self._interrupted = False
        self._thread_id = threading.get_ident() if hasattr(threading, "get_ident") else None
        clear_interrupt(self._thread_id)
        if self._guardrails:
            self._guardrails.reset_for_turn()

        if not self._messages:
            if self.system_prompt:
                self._messages.append({"role": "system", "content": self.system_prompt})

        self._messages.append({"role": "user", "content": user_message})

        final_text = None
        final_reasoning = None
        status = LoopStatus.RUNNING
        iteration = 0

        while status == LoopStatus.RUNNING and iteration < self.config.max_iterations:
            if self._interrupted:
                status = LoopStatus.INTERRUPTED
                break

            iteration += 1

            if self.callbacks.on_iteration:
                self.callbacks.on_iteration(iteration, status)

            response = self._call_llm_with_retry()

            if response is None:
                status = LoopStatus.ERROR
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
            status = LoopStatus.COMPLETED

        if status == LoopStatus.RUNNING:
            status = LoopStatus.TOOL_LIMIT

        if final_text:
            self._messages.append({"role": "assistant", "content": final_text})

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
        )

    def _estimate_tokens(self, messages: list[dict]) -> int:
        """Rough token estimate: ~4 chars per token."""
        total = 0
        for m in messages:
            content = m.get("content") or ""
            total += len(str(content)) // 4
        return total

    def _compress_context(self, messages: list[dict]) -> list[dict]:
        """LLM-backed compression when over token budget."""
        compressed, summary, did = compress_messages(
            messages,
            max_tokens=self.config.max_context_tokens,
            previous_summary=self._compression_summary,
        )
        if did and summary:
            self._compression_summary = summary
        return compressed

    def _prepare_messages_for_api(self) -> list[dict]:
        messages = self._compress_context(list(self._messages))
        messages, _ = repair_message_sequence(messages)
        repair_tool_arguments(messages)
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
        return True

    def _call_llm_with_retry(self) -> Optional[NormalizedResponse]:
        """Call LLM with classified retry, compression, and provider fallback."""
        messages_to_send = self._prepare_messages_for_api()

        if self.callbacks.on_llm_start:
            self.callbacks.on_llm_start(messages_to_send)

        last_error: Exception | None = None
        compress_attempted = False

        for attempt in range(self.config.max_retries):
            if self._interrupted or (self._thread_id and is_interrupted(self._thread_id)):
                return None

            try:
                if self.config.stream and self.callbacks.on_stream_delta:
                    response = self.client.stream(
                        messages=messages_to_send,
                        tools=self.tools if self.tools else None,
                        on_delta=self.callbacks.on_stream_delta,
                    )
                else:
                    response = self.client.complete(
                        messages=messages_to_send,
                        tools=self.tools if self.tools else None,
                    )

                if self.callbacks.on_llm_complete:
                    self.callbacks.on_llm_complete(response)

                return response

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
                    time.sleep(self.config.retry_delay * (attempt + 1))

        logger.error("All LLM attempts failed: %s", last_error)
        return None

    def _process_tool_calls(self, response: NormalizedResponse) -> None:
        """Dispatch tool calls (parallel when safe) with guardrails."""
        if not response.tool_calls:
            return

        assistant_msg: dict[str, Any] = {"role": "assistant", "content": response.content}
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

        check = lambda: self._interrupted or (
            self._thread_id is not None and is_interrupted(self._thread_id)
        )

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

    def _dispatch_tool(self, name: str, args: dict) -> str:
        """Dispatch a tool call through Butler's registry."""
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

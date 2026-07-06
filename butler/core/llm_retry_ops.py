"""LLM retry failure handling extracted from ``llm_retry`` (P0-A)."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

from butler.core.llm_retry_errors import handle_classified_llm_error
from butler.core.llm_retry_helpers import prepare_tools_for_llm, try_exp_cache_response
from butler.core.llm_retry_invoke import execute_llm_call
from butler.core.llm_retry_outcomes import record_llm_failure, record_llm_interrupt
from butler.core.llm_retry_success import process_llm_response
from butler.core.loop_types import LoopCallbacks, LoopConfig
from butler.transport.error_classifier import classify_api_error
from butler.transport.llm_client import LLMClient
from butler.transport.types import NormalizedResponse

logger = logging.getLogger(__name__)


@dataclass
class LlmAttemptFailureUpdate:
    last_error: Exception
    tools_to_send: list[dict[str, Any]] | None
    messages_to_send: list[dict[str, Any]] | None
    compress_attempted: bool
    schema_recovery_attempted: bool
    action: str


def handle_llm_attempt_exception(
    exc: Exception,
    *,
    attempt: int,
    config: LoopConfig,
    callbacks: LoopCallbacks,
    client: Any,
    messages: list[dict[str, Any]],
    messages_to_send: list[dict[str, Any]],
    tools_to_send: list[dict[str, Any]],
    compress_attempted: bool,
    schema_recovery_attempted: bool,
    compress_messages: Callable[[list[dict[str, Any]]], list[dict[str, Any]]],
    prepare_messages: Callable[[], list[dict[str, Any]]],
    diagnostics: dict[str, Any],
    try_activate_fallback: Callable[[], bool],
) -> LlmAttemptFailureUpdate:
    classified = classify_api_error(
        exc,
        provider=getattr(client, "provider_name", ""),
        model=getattr(client, "model", ""),
    )
    logger.warning(
        "LLM attempt %d/%d failed [%s]: %s",
        attempt + 1,
        config.max_retries,
        classified.reason.value,
        exc,
    )
    step, compress_attempted, schema_recovery_attempted = handle_classified_llm_error(
        exc=exc,
        classified=classified,
        attempt=attempt,
        config=config,
        callbacks=callbacks,
        messages=messages,
        messages_to_send=messages_to_send,
        tools_to_send=tools_to_send,
        compress_attempted=compress_attempted,
        schema_recovery_attempted=schema_recovery_attempted,
        compress_messages=compress_messages,
        prepare_messages=prepare_messages,
        diagnostics=diagnostics,
        try_activate_fallback=try_activate_fallback,
    )
    tools = step.tools_to_send if step.tools_to_send is not None else tools_to_send
    msgs = step.messages_to_send if step.messages_to_send is not None else messages_to_send
    return LlmAttemptFailureUpdate(
        last_error=exc,
        tools_to_send=tools,
        messages_to_send=msgs,
        compress_attempted=compress_attempted,
        schema_recovery_attempted=schema_recovery_attempted,
        action=step.action,
    )


def run_llm_with_retry_loop(
    *,
    client: LLMClient,
    config: LoopConfig,
    callbacks: LoopCallbacks,
    tools: list[dict[str, Any]],
    messages: list[dict[str, Any]],
    diagnostics: dict[str, Any],
    prepare_messages: Callable[[], list[dict[str, Any]]],
    compress_messages: Callable[[list[dict[str, Any]]], list[dict[str, Any]]],
    interrupt_check: Callable[[], bool],
    try_activate_fallback: Callable[[], bool],
    empty_retries: list[int],
    messages_to_send: list[dict[str, Any]],
    tools_to_send: list[dict[str, Any]],
    cache_fp: str | None,
    on_tool_call_ready: Callable[[int, str, str, dict[str, Any]], None] | None = None,
) -> tuple[Optional[NormalizedResponse], bool, Exception | None]:
    """Retry loop body; returns (response, interrupted, last_error)."""
    last_error: Exception | None = None
    compress_attempted = False
    schema_recovery_attempted = False
    interrupted = False
    effective_retries = min(config.max_retries, 20)

    for attempt in range(effective_retries):
        if interrupt_check():
            return None, True, None

        try:
            common = {
                "messages": messages_to_send,
                "tools": tools_to_send,
                "check_interrupt": interrupt_check,
                "stale_timeout": config.api_stale_timeout,
            }
            llm_started = time.monotonic()
            raw = execute_llm_call(
                client=client,
                config=config,
                common=common,
                on_delta_cb=callbacks.on_stream_delta,
                on_tool_call_ready=on_tool_call_ready,
            )
            early, refreshed, done = process_llm_response(
                raw_response=raw,
                client=client,
                config=config,
                callbacks=callbacks,
                messages=messages,
                prepare_messages=prepare_messages,
                diagnostics=diagnostics,
                cache_fp=cache_fp,
                llm_started=llm_started,
                empty_retries=empty_retries,
            )
            if done:
                if early is not None:
                    return early, False, None
                return None, False, None
            if refreshed is not None:
                messages_to_send = refreshed
                continue

        except InterruptedError:
            record_llm_interrupt(client)
            return None, True, None

        except Exception as exc:
            update = handle_llm_attempt_exception(
                exc,
                attempt=attempt,
                config=config,
                callbacks=callbacks,
                client=client,
                messages=messages,
                messages_to_send=messages_to_send,
                tools_to_send=tools_to_send,
                compress_attempted=compress_attempted,
                schema_recovery_attempted=schema_recovery_attempted,
                compress_messages=compress_messages,
                prepare_messages=prepare_messages,
                diagnostics=diagnostics,
                try_activate_fallback=try_activate_fallback,
            )
            last_error = update.last_error
            tools_to_send = update.tools_to_send or tools_to_send
            messages_to_send = update.messages_to_send or messages_to_send
            compress_attempted = update.compress_attempted
            schema_recovery_attempted = update.schema_recovery_attempted
            if update.action == "break":
                break
            if update.action in ("continue", "sleep_continue"):
                continue

    return None, interrupted, last_error

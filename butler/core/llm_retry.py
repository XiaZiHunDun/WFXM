"""LLM call retry loop extracted from AgentLoop."""

from __future__ import annotations

import logging
import time
from typing import Any, Callable, Optional

from butler.core.llm_retry_errors import handle_classified_llm_error
from butler.core.llm_retry_helpers import (
    prepare_tools_for_llm,
    try_exp_cache_response,
)
from butler.core.llm_retry_invoke import execute_llm_call
from butler.core.llm_retry_outcomes import record_llm_failure, record_llm_interrupt
from butler.core.llm_retry_safe import safe_call
from butler.core.llm_retry_success import process_llm_response
from butler.core.loop_types import LoopCallbacks, LoopConfig
from butler.transport.error_classifier import classify_api_error
from butler.transport.llm_client import LLMClient
from butler.transport.types import NormalizedResponse

logger = logging.getLogger(__name__)


def _safe_call(fn: Callable[[], Any], msg: str) -> Any:
    return safe_call(fn, msg, _logger=logger)


def call_llm_with_retry(
    *,
    client: LLMClient,
    config: LoopConfig,
    callbacks: LoopCallbacks,
    tools: list[dict],
    messages: list[dict],
    diagnostics: dict[str, Any],
    prepare_messages: Callable[[], list[dict]],
    compress_messages: Callable[[list[dict]], list[dict]],
    interrupt_check: Callable[[], bool],
    try_activate_fallback: Callable[[], bool],
    empty_retries: list[int],
    on_tool_call_ready: Callable[[int, str, str, dict], None] | None = None,
) -> tuple[Optional[NormalizedResponse], bool]:
    """Call the LLM with retries; return (response, interrupted)."""
    from butler.core.preemptive_compact import prepare_messages_or_abort

    messages_to_send = prepare_messages_or_abort(prepare_messages, diagnostics)
    if messages_to_send is None:
        return None, False
    if callbacks.on_llm_start:
        callbacks.on_llm_start(messages_to_send)

    last_error: Exception | None = None
    compress_attempted = False
    schema_recovery_attempted = False
    tools_to_send = prepare_tools_for_llm(tools, client=client, diagnostics=diagnostics)
    interrupted = False

    cache_fp, cached = try_exp_cache_response(
        client=client,
        messages=messages_to_send,
        tools_to_send=tools_to_send,
        diagnostics=diagnostics,
    )
    if cached is not None:
        return cached, False

    effective_retries = min(config.max_retries, 20)
    for attempt in range(effective_retries):
        if interrupt_check():
            return None, True

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
                    return early, False
                return None, False
            if refreshed is not None:
                messages_to_send = refreshed
                continue

        except InterruptedError:
            record_llm_interrupt(client)
            return None, True

        except Exception as exc:
            last_error = exc
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
            if step.tools_to_send is not None:
                tools_to_send = step.tools_to_send
            if step.messages_to_send is not None:
                messages_to_send = step.messages_to_send
            if step.action == "break":
                break
            if step.action in ("continue", "sleep_continue"):
                continue

    logger.error("All LLM attempts failed: %s", last_error, exc_info=last_error)
    record_llm_failure(client, last_error)
    return None, interrupted


__all__ = ["_safe_call", "call_llm_with_retry"]

"""LLM call retry loop extracted from AgentLoop."""

from __future__ import annotations

import logging
import time
from typing import Any, Callable, Optional

from butler.core.loop_response import empty_retry_message, needs_empty_content_retry, sanitize_response
from butler.core.loop_types import LoopCallbacks, LoopConfig
from butler.core.retry_policy import retry_delay_for_config
from butler.core.schema_recovery import recover_schema_after_error
from butler.transport.error_classifier import classify_api_error
from butler.transport.interruptible_client import StaleApiCallError
from butler.transport.llm_client import LLMClient
from butler.transport.types import NormalizedResponse

logger = logging.getLogger(__name__)


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
) -> tuple[Optional[NormalizedResponse], bool]:
    """Call the LLM with retries; return (response, interrupted)."""
    messages_to_send = prepare_messages()
    if callbacks.on_llm_start:
        callbacks.on_llm_start(messages_to_send)

    last_error: Exception | None = None
    compress_attempted = False
    schema_recovery_attempted = False
    tools_to_send = tools or None
    interrupted = False

    for attempt in range(config.max_retries):
        if interrupt_check():
            return None, True

        try:
            common = {
                "messages": messages_to_send,
                "tools": tools_to_send,
                "check_interrupt": interrupt_check,
                "stale_timeout": config.api_stale_timeout,
            }
            if config.stream and callbacks.on_stream_delta:
                response = client.stream(
                    on_delta=callbacks.on_stream_delta,
                    **common,
                )
            else:
                response = client.complete(**common)

            response = sanitize_response(response)

            if (
                needs_empty_content_retry(response)
                and empty_retries[0] < config.max_empty_content_retries
            ):
                empty_retries[0] += 1
                messages.append({"role": "user", "content": empty_retry_message()})
                messages_to_send = prepare_messages()
                continue

            if callbacks.on_llm_complete:
                callbacks.on_llm_complete(response)
            return response, False

        except InterruptedError:
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
            if callbacks.on_error:
                callbacks.on_error(exc, attempt + 1)

            if isinstance(exc, StaleApiCallError) and classified.retryable:
                if attempt < config.max_retries - 1:
                    time.sleep(retry_delay_for_config(config, attempt))
                    continue

            if tools_to_send and not schema_recovery_attempted:
                recovered = recover_schema_after_error(
                    exc,
                    tools_to_send,
                    diagnostics=diagnostics,
                )
                schema_recovery_attempted = schema_recovery_attempted or recovered.attempted
                if recovered.attempted and recovered.tools is not None:
                    tools_to_send = recovered.tools
                if recovered.recovered:
                    if attempt < config.max_retries - 1:
                        logger.info(
                            "Retrying LLM call after stripping %d schema pattern/format keywords",
                            recovered.stripped,
                        )
                        continue

            if classified.should_compress and not compress_attempted:
                compress_attempted = True
                messages[:] = compress_messages(list(messages))
                messages_to_send = prepare_messages()
                continue

            if classified.should_fallback and try_activate_fallback():
                continue

            if not classified.retryable:
                break

            if attempt < config.max_retries - 1:
                time.sleep(retry_delay_for_config(config, attempt))

    logger.error("All LLM attempts failed: %s", last_error)
    return None, interrupted

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
            provider = str(getattr(client, "provider_name", "") or "?")[:24]
            llm_started = time.monotonic()
            on_delta_cb = callbacks.on_stream_delta
            if on_delta_cb:
                from butler.transport.memory_context_scrubber import (
                    StreamingMemoryContextScrubber,
                    memory_stream_scrub_enabled,
                    scrub_stream_delta,
                )

                if memory_stream_scrub_enabled():
                    scrubber = StreamingMemoryContextScrubber()
                    base_delta = on_delta_cb

                    def on_delta_cb(chunk: str) -> None:  # type: ignore[misc]
                        cleaned = scrub_stream_delta(chunk, scrubber)
                        if cleaned:
                            base_delta(cleaned)

            if config.stream and (on_delta_cb or on_tool_call_ready):
                response = client.stream(
                    on_delta=on_delta_cb,
                    on_tool_call_ready=on_tool_call_ready,
                    **common,
                )
            else:
                response = client.complete(**common)

            response = sanitize_response(response)
            try:
                from butler.ops.runtime_metrics import inc, observe_ms

                observe_ms(
                    "llm_latency",
                    (time.monotonic() - llm_started) * 1000.0,
                    labels={"provider": provider, "outcome": "ok"},
                )
                inc("llm_request", labels={"provider": provider, "outcome": "ok"})
            except Exception:
                pass

            if (
                needs_empty_content_retry(response)
                and empty_retries[0] < config.max_empty_content_retries
            ):
                empty_retries[0] += 1
                messages.append({"role": "user", "content": empty_retry_message()})
                messages_to_send = prepare_messages_or_abort(prepare_messages, diagnostics)
                if messages_to_send is None:
                    return None, False
                continue

            if callbacks.on_llm_complete:
                callbacks.on_llm_complete(response)
            return response, False

        except InterruptedError:
            try:
                from butler.ops.runtime_metrics import inc

                provider = str(getattr(client, "provider_name", "") or "?")[:24]
                inc("llm_request", labels={"provider": provider, "outcome": "interrupt"})
            except Exception:
                pass
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
                diagnostics["reactive_compact_reason"] = classified.reason.value
                try:
                    from butler.ops.retry_buckets import record_recovery_event

                    record_recovery_event("reactive_compact")
                except Exception:
                    pass
                from butler.core.reactive_compact import apply_reactive_compact_to_messages

                applied = apply_reactive_compact_to_messages(
                    messages,
                    compress_fn=compress_messages,
                    diagnostics=diagnostics,
                )
                if not applied:
                    messages[:] = compress_messages(list(messages))
                    diagnostics["reactive_context_compact"] = True
                messages_to_send = prepare_messages_or_abort(prepare_messages, diagnostics)
                if messages_to_send is None:
                    return None, False
                continue

            if classified.should_fallback and try_activate_fallback():
                try:
                    from butler.ops.retry_buckets import record_recovery_event

                    record_recovery_event("provider_failover")
                except Exception:
                    pass
                continue

            if not classified.retryable:
                break

            if attempt < config.max_retries - 1:
                time.sleep(retry_delay_for_config(config, attempt))

    logger.error("All LLM attempts failed: %s", last_error)
    try:
        from butler.ops.runtime_metrics import inc

        provider = str(getattr(client, "provider_name", "") or "?")[:24]
        inc("llm_request", labels={"provider": provider, "outcome": "fail"})
    except Exception:
        pass
    return None, interrupted

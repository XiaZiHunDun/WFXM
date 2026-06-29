"""Classified-error retry policy for ``call_llm_with_retry``."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from butler.core.llm_retry_helpers import apply_reactive_compact_retry
from butler.core.llm_retry_safe import safe_call
from butler.core.loop_types import LoopCallbacks, LoopConfig
from butler.core.retry_policy import retry_delay_for_config
from butler.core.schema_recovery import recover_schema_after_error
from butler.transport.error_classifier import ClassifiedError
from butler.transport.interruptible_client import StaleApiCallError

RetryAction = Literal["continue", "break", "sleep_continue"]


@dataclass
class LlmRetryStep:
    action: RetryAction
    messages_to_send: list[dict] | None = None
    tools_to_send: list[dict] | None = None


def handle_classified_llm_error(
    *,
    exc: Exception,
    classified: ClassifiedError,
    attempt: int,
    config: LoopConfig,
    callbacks: LoopCallbacks,
    messages: list[dict],
    messages_to_send: list[dict],
    tools_to_send: list[dict] | None,
    compress_attempted: bool,
    schema_recovery_attempted: bool,
    compress_messages: Callable[[list[dict]], list[dict]],
    prepare_messages: Callable[[], list[dict]],
    diagnostics: dict[str, Any],
    try_activate_fallback: Callable[[], bool],
) -> tuple[LlmRetryStep, bool, bool]:
    """Return (step, compress_attempted, schema_recovery_attempted)."""
    if callbacks.on_error:
        callbacks.on_error(exc, attempt + 1)

    if isinstance(exc, StaleApiCallError) and classified.retryable:
        if attempt < config.max_retries - 1:
            time.sleep(retry_delay_for_config(config, attempt))
            return LlmRetryStep("continue"), compress_attempted, schema_recovery_attempted

    if tools_to_send and not schema_recovery_attempted:
        recovered = recover_schema_after_error(
            exc,
            tools_to_send,
            diagnostics=diagnostics,
        )
        schema_recovery_attempted = schema_recovery_attempted or recovered.attempted
        tools = tools_to_send
        if recovered.attempted and recovered.tools is not None:
            tools = recovered.tools
        if recovered.recovered and attempt < config.max_retries - 1:
            return (
                LlmRetryStep("continue", tools_to_send=tools),
                compress_attempted,
                schema_recovery_attempted,
            )

    if classified.should_compress and not compress_attempted:
        refreshed = apply_reactive_compact_retry(
            messages=messages,
            compress_messages=compress_messages,
            prepare_messages=prepare_messages,
            diagnostics=diagnostics,
        )
        if refreshed is None:
            return LlmRetryStep("break"), True, schema_recovery_attempted
        diagnostics["reactive_compact_reason"] = classified.reason.value
        return (
            LlmRetryStep("continue", messages_to_send=refreshed),
            True,
            schema_recovery_attempted,
        )

    if classified.should_fallback and try_activate_fallback():

        def _record_provider_failover() -> None:
            from butler.ops.retry_buckets import record_recovery_event

            record_recovery_event("provider_failover")

        safe_call(_record_provider_failover, "record provider failover skipped")
        return LlmRetryStep("continue"), compress_attempted, schema_recovery_attempted

    if not classified.retryable:
        return LlmRetryStep("break"), compress_attempted, schema_recovery_attempted

    if attempt < config.max_retries - 1:
        time.sleep(retry_delay_for_config(config, attempt))
        return LlmRetryStep("sleep_continue"), compress_attempted, schema_recovery_attempted

    return LlmRetryStep("break"), compress_attempted, schema_recovery_attempted


__all__ = ["LlmRetryStep", "handle_classified_llm_error"]

"""LLM retry failure handling extracted from ``llm_retry`` (P0-A)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

from butler.core.llm_retry_errors import handle_classified_llm_error
from butler.core.loop_types import LoopCallbacks, LoopConfig
from butler.transport.error_classifier import classify_api_error

logger = logging.getLogger(__name__)


@dataclass
class LlmAttemptFailureUpdate:
    last_error: Exception
    tools_to_send: list[dict] | None
    messages_to_send: list[dict] | None
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
    messages: list[dict],
    messages_to_send: list[dict],
    tools_to_send: list[dict],
    compress_attempted: bool,
    schema_recovery_attempted: bool,
    compress_messages: Callable[[list[dict]], list[dict]],
    prepare_messages: Callable[[], list[dict]],
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

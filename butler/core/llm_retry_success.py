"""Successful LLM response handling for ``call_llm_with_retry``."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from butler.core.llm_retry_helpers import record_llm_success_side_effects
from butler.core.llm_retry_safe import safe_call
from butler.core.loop_response import empty_retry_message, needs_empty_content_retry, sanitize_response
from butler.core.loop_types import LoopCallbacks, LoopConfig
from butler.transport.llm_client import LLMClient
from butler.transport.types import NormalizedResponse


def process_llm_response(
    *,
    raw_response: NormalizedResponse,
    client: LLMClient,
    config: LoopConfig,
    callbacks: LoopCallbacks,
    messages: list[dict],
    prepare_messages: Callable[[], list[dict]],
    diagnostics: dict[str, Any],
    cache_fp: str,
    llm_started: float,
    empty_retries: list[int],
) -> tuple[NormalizedResponse | None, list[dict] | None, bool]:
    """Return (early_response, refreshed_messages_to_send, done).

    When ``done`` is True, caller should return ``early_response``.
    ``refreshed_messages_to_send`` is set when empty-content retry needs another attempt.
    """
    response = sanitize_response(raw_response)

    def _safety_finish() -> bool:
        from butler.core.safety_finish import safety_finish_user_message

        safety_msg = safety_finish_user_message(response)
        if not safety_msg:
            return False
        response.tool_calls = None
        response.content = safety_msg
        response.finish_reason = "stop"
        if callbacks.on_llm_complete:
            callbacks.on_llm_complete(response)
        return True

    if safe_call(_safety_finish, "safety finish skipped"):
        return response, None, True

    record_llm_success_side_effects(
        client=client,
        response=response,
        cache_fp=cache_fp,
        llm_started=llm_started,
        diagnostics=diagnostics,
    )
    if (
        needs_empty_content_retry(response)
        and empty_retries[0] < config.max_empty_content_retries
    ):
        empty_retries[0] += 1
        messages.append({"role": "user", "content": empty_retry_message()})
        from butler.core.preemptive_compact import prepare_messages_or_abort

        refreshed = prepare_messages_or_abort(prepare_messages, diagnostics)
        return None, refreshed, refreshed is None

    if callbacks.on_llm_complete:
        callbacks.on_llm_complete(response)
    return response, None, True


__all__ = ["process_llm_response"]

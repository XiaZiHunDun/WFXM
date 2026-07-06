"""LLM call retry loop extracted from AgentLoop."""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from butler.core.llm_retry_helpers import prepare_tools_for_llm, try_exp_cache_response
from butler.core.llm_retry_outcomes import record_llm_failure
from butler.core.llm_retry_safe import safe_call
from butler.core.loop_types import LoopCallbacks, LoopConfig
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
    tools: list[dict[str, Any]],
    messages: list[dict[str, Any]],
    diagnostics: dict[str, Any],
    prepare_messages: Callable[[], list[dict[str, Any]]],
    compress_messages: Callable[[list[dict[str, Any]]], list[dict[str, Any]]],
    interrupt_check: Callable[[], bool],
    try_activate_fallback: Callable[[], bool],
    empty_retries: list[int],
    on_tool_call_ready: Callable[[int, str, str, dict[str, Any]], None] | None = None,
) -> tuple[Optional[NormalizedResponse], bool]:
    """Call the LLM with retries; return (response, interrupted)."""
    from butler.core.llm_retry_ops import run_llm_with_retry_loop
    from butler.core.preemptive_compact import prepare_messages_or_abort

    messages_to_send = prepare_messages_or_abort(prepare_messages, diagnostics)
    if messages_to_send is None:
        return None, False
    if callbacks.on_llm_start:
        callbacks.on_llm_start(messages_to_send)

    tools_to_send = prepare_tools_for_llm(tools, client=client, diagnostics=diagnostics)
    cache_fp, cached = try_exp_cache_response(
        client=client,
        messages=messages_to_send,
        tools_to_send=tools_to_send,
        diagnostics=diagnostics,
    )
    if cached is not None:
        return cached, False

    response, interrupted, last_error = run_llm_with_retry_loop(
        client=client,
        config=config,
        callbacks=callbacks,
        tools=tools,
        messages=messages,
        diagnostics=diagnostics,
        prepare_messages=prepare_messages,
        compress_messages=compress_messages,
        interrupt_check=interrupt_check,
        try_activate_fallback=try_activate_fallback,
        empty_retries=empty_retries,
        messages_to_send=messages_to_send,
        tools_to_send=tools_to_send,
        cache_fp=cache_fp,
        on_tool_call_ready=on_tool_call_ready,
    )
    if response is not None or interrupted:
        return response, interrupted

    logger.error("All LLM attempts failed: %s", last_error, exc_info=last_error)
    record_llm_failure(client, last_error)
    return None, interrupted


__all__ = ["_safe_call", "call_llm_with_retry"]

"""LLM client invocation helpers for ``call_llm_with_retry``."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from butler.core.loop_types import LoopConfig
from butler.transport.llm_client import LLMClient
from butler.transport.types import NormalizedResponse


def prepare_stream_delta_callback(
    on_delta_cb: Callable[[str], None] | None,
) -> Callable[[str], None] | None:
    if not on_delta_cb:
        return None
    from butler.transport.memory_context_scrubber import (
        StreamingMemoryContextScrubber,
        memory_stream_scrub_enabled,
        scrub_stream_delta,
    )

    if not memory_stream_scrub_enabled():
        return on_delta_cb

    scrubber = StreamingMemoryContextScrubber()
    base_delta = on_delta_cb

    def wrapped(chunk: str) -> None:
        cleaned = scrub_stream_delta(chunk, scrubber)
        if cleaned:
            base_delta(cleaned)

    return wrapped


def execute_llm_call(
    *,
    client: LLMClient,
    config: LoopConfig,
    common: dict[str, Any],
    on_delta_cb: Callable[[str], None] | None,
    on_tool_call_ready: Callable[[int, str, str, dict], None] | None,
) -> NormalizedResponse:
    delta = prepare_stream_delta_callback(on_delta_cb)
    if config.stream and (delta or on_tool_call_ready):
        return client.stream(
            on_delta=delta,
            on_tool_call_ready=on_tool_call_ready,
            **common,
        )
    return client.complete(**common)


__all__ = ["execute_llm_call", "prepare_stream_delta_callback"]

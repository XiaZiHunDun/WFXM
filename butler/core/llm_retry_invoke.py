"""LLM client invocation helpers for ``call_llm_with_retry``."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from butler.core.loop_types import LoopConfig
from butler.core.structured_events import emit_llm_api_call, prompt_hash_from_messages
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
    started = time.monotonic()
    status = "ok"
    resp: NormalizedResponse | None = None
    try:
        if config.stream and (delta or on_tool_call_ready):
            resp = client.stream(
                on_delta=delta,
                on_tool_call_ready=on_tool_call_ready,
                **common,
            )
        else:
            resp = client.complete(**common)
    except Exception:
        status = "error"
        raise
    finally:
        duration_ms = (time.monotonic() - started) * 1000.0
        usage = getattr(resp, "usage", None) if resp is not None else None
        token_in = token_out = 0
        if usage is not None:
            token_in = int(getattr(usage, "input_tokens", 0) or 0)
            token_out = int(getattr(usage, "output_tokens", 0) or 0)
        try:
            from butler.execution_context import get_current_session_key

            sk = str(get_current_session_key() or "")
        except Exception:
            sk = ""
        emit_llm_api_call(
            duration_ms=duration_ms,
            status=status,
            provider=str(getattr(client, "provider", "") or common.get("provider") or ""),
            prompt_hash=prompt_hash_from_messages(common.get("messages")),
            token_in=token_in,
            token_out=token_out,
            session_key=sk,
        )
    assert resp is not None
    return resp


__all__ = ["execute_llm_call", "prepare_stream_delta_callback"]

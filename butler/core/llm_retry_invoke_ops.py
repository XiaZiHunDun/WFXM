"""LLM invoke telemetry helpers (P0-A)."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from butler.core.best_effort import safe_best_effort
from butler.core.loop_types import LoopConfig
from butler.core.structured_events import emit_llm_api_call, prompt_hash_from_messages
from butler.transport.llm_client import LLMClient
from butler.transport.types import NormalizedResponse


def current_llm_telemetry_session_key_safe() -> str:
    def _run() -> str:
        from butler.execution_context import get_current_session_key

        return str(get_current_session_key() or "")

    result = safe_best_effort(
        _run,
        label="llm_retry_invoke.session_key",
        default="",
    )
    return str(result or "")


def execute_llm_call_ops(
    *,
    client: LLMClient,
    config: LoopConfig,
    common: dict[str, Any],
    delta: Callable[[str], None] | None,
    on_tool_call_ready: Callable[[int, str, str, dict], None] | None,
) -> NormalizedResponse:
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
        sk = current_llm_telemetry_session_key_safe()
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

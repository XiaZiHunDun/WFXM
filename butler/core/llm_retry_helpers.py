"""Helpers extracted from ``call_llm_with_retry`` (P1-C)."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any, cast

from butler.core.llm_retry_safe import safe_call as _safe_call
from butler.transport.llm_client import LLMClient
from butler.transport.types import NormalizedResponse


def prepare_tools_for_llm(
    tools: list[dict[str, Any]] | None,
    *,
    client: LLMClient,
    diagnostics: dict[str, Any],
) -> list[dict[str, Any]] | None:
    """Optimize and filter tool schemas before an LLM call."""
    tools_to_send = tools or None
    if not tools_to_send:
        return None

    def _optimize() -> None:
        from butler.core.schema_optimizer import optimize_tool_definitions

        nonlocal tools_to_send
        tools_to_send = optimize_tool_definitions(
            tools_to_send,
            diagnostics=diagnostics,
            provider=str(getattr(client, "provider_name", "") or ""),
        )

    _safe_call(_optimize, "call llm with retry skipped")
    if tools_to_send:

        def _filter() -> None:
            from butler.mcp.tools_engine import filter_tools_for_model

            nonlocal tools_to_send
            tools_to_send, te_diag = filter_tools_for_model(
                tools_to_send,
                provider=str(getattr(client, "provider_name", "") or ""),
                model=str(getattr(client, "model", "") or ""),
            )
            diagnostics.update(te_diag)

        _safe_call(_filter, "call llm with retry skipped")
    return tools_to_send


def try_exp_cache_response(
    *,
    client: LLMClient,
    messages: list[dict[str, Any]],
    tools_to_send: list[dict[str, Any]] | None,
    diagnostics: dict[str, Any],
) -> tuple[str, NormalizedResponse | None]:
    """Return (cache_fp, cached_response) when exp_cache hits."""
    cache_fp = ""

    def _lookup() -> NormalizedResponse | None:
        nonlocal cache_fp
        from butler.core.exp_cache import (
            fingerprint_llm_request,
            lookup_cached_response,
        )
        from butler.core.meta_flags import exp_cache_enabled

        if not (exp_cache_enabled() and not tools_to_send):
            return None
        cache_fp = fingerprint_llm_request(
            provider=str(getattr(client, "provider_name", "") or ""),
            model=str(getattr(client, "model", "") or ""),
            messages=messages,
            tools=tools_to_send,
        )
        cached_text = lookup_cached_response(cache_fp)
        if not cached_text:
            return None
        return NormalizedResponse(content=cached_text, finish_reason="stop")

    resp = _safe_call(_lookup, "exp_cache lookup skipped")
    if resp is not None:
        diagnostics["exp_cache_hit"] = True
        return cache_fp, resp
    return cache_fp, None


def record_llm_success_side_effects(
    *,
    client: LLMClient,
    response: NormalizedResponse,
    cache_fp: str,
    llm_started: float,
    diagnostics: dict[str, Any],
) -> None:
    provider = str(getattr(client, "provider_name", "") or "?")[:24]

    def _record_ok_latency() -> None:
        from butler.ops.runtime_metrics import inc, observe_ms

        observe_ms(
            "llm_latency",
            (time.monotonic() - llm_started) * 1000.0,
            labels={"provider": provider, "outcome": "ok"},
        )
        inc("llm_request", labels={"provider": provider, "outcome": "ok"})

    _safe_call(_record_ok_latency, "record ok latency skipped")

    def _record_provider_success() -> None:
        from butler.transport.provider_health import record_provider_success

        record_provider_success(
            str(getattr(client, "provider", "") or ""),
            str(getattr(client, "model", "") or ""),
        )

    _safe_call(_record_provider_success, "record provider success skipped")

    if cache_fp and response and not response.tool_calls:

        def _exp_cache_store() -> None:
            from butler.core.exp_cache import store_cached_response

            fr = getattr(response, "finish_reason", None) or ""
            text = str(response.content or "").strip()
            if text and fr not in ("error", "content_filter"):
                store_cached_response(
                    cache_fp,
                    text,
                    provider=str(getattr(client, "provider_name", "") or ""),
                    model=str(getattr(client, "model", "") or ""),
                )
                diagnostics["exp_cache_store"] = True

        _safe_call(_exp_cache_store, "exp_cache store skipped")


def apply_reactive_compact_retry(
    *,
    messages: list[dict[str, Any]],
    compress_messages: Callable[[list[dict[str, Any]]], list[dict[str, Any]]],
    prepare_messages: Callable[[], list[dict[str, Any]]],
    diagnostics: dict[str, Any],
) -> list[dict[str, Any]] | None:
    """Run reactive compact; return refreshed messages_to_send or None to abort."""

    def _record_reactive_compact() -> None:
        from butler.ops.retry_buckets import record_recovery_event

        record_recovery_event("reactive_compact")

    _safe_call(_record_reactive_compact, "record reactive compact skipped")
    from butler.core.preemptive_compact import prepare_messages_or_abort
    from butler.core.reactive_compact import apply_reactive_compact_to_messages

    applied = apply_reactive_compact_to_messages(
        messages,
        compress_fn=compress_messages,
        diagnostics=diagnostics,
    )
    if not applied:
        messages[:] = compress_messages(list(messages))
        diagnostics["reactive_context_compact"] = True
    return cast(
        "list[dict[str, Any]] | None",
        prepare_messages_or_abort(prepare_messages, diagnostics),
    )


__all__ = [
    "apply_reactive_compact_retry",
    "prepare_tools_for_llm",
    "record_llm_success_side_effects",
    "try_exp_cache_response",
]

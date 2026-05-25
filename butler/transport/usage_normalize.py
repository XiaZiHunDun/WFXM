"""Normalize LLM usage across OpenAI / Anthropic / MiniMax transports (Langflow subset)."""

from __future__ import annotations

from typing import Any

from butler.transport.types import Usage


def _int_field(raw: Any, *keys: str) -> int:
    if raw is None:
        return 0
    if isinstance(raw, dict):
        for key in keys:
            if key in raw and raw[key] is not None:
                try:
                    return max(0, int(raw[key]))
                except (TypeError, ValueError):
                    continue
        return 0
    for key in keys:
        val = getattr(raw, key, None)
        if val is not None:
            try:
                return max(0, int(val))
            except (TypeError, ValueError):
                continue
    return 0


def normalize_usage(
    raw: Any,
    *,
    provider: str = "",
) -> Usage | None:
    """Map provider-specific usage blobs to :class:`Usage`."""
    if raw is None:
        return None

    prompt = _int_field(
        raw,
        "prompt_tokens",
        "input_tokens",
        "prompt_token_count",
    )
    completion = _int_field(
        raw,
        "completion_tokens",
        "output_tokens",
        "completion_token_count",
    )
    total = _int_field(raw, "total_tokens", "total_token_count")
    cached = _int_field(
        raw,
        "cached_tokens",
        "cache_read_input_tokens",
        "cache_creation_input_tokens",
    )

    if prompt == 0 and completion == 0 and total == 0 and cached == 0:
        return None

    if total <= 0:
        total = prompt + completion + cached

    return Usage(
        prompt_tokens=prompt,
        completion_tokens=completion,
        total_tokens=total,
        cached_tokens=cached,
    )


def normalize_usage_from_response(
    response: Any,
    *,
    provider: str = "",
) -> Usage | None:
    usage = getattr(response, "usage", None)
    if usage is None and isinstance(response, dict):
        usage = response.get("usage")
    if isinstance(usage, Usage):
        return usage
    return normalize_usage(usage, provider=provider)


def usage_to_diagnostics_fields(usage: Usage | None) -> dict[str, int]:
    if usage is None:
        return {}
    return {
        "last_usage_prompt_tokens": int(usage.prompt_tokens or 0),
        "last_usage_completion_tokens": int(usage.completion_tokens or 0),
        "last_usage_total_tokens": int(usage.total_tokens or 0),
        "last_usage_cached_tokens": int(usage.cached_tokens or 0),
    }

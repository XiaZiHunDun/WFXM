"""LLM client best-effort / fail-safe helpers (P0-A)."""

from __future__ import annotations

import logging
from typing import Any, Callable, cast

logger = logging.getLogger(__name__)


def wire_tools_or_empty_loud(
    provider_name: str,
    tools: list[dict[str, Any]],
    *,
    api_mode: str,
) -> tuple[list[dict[str, Any]], BaseException | None]:
    from butler.transport.tool_wire import wire_tools_for_provider

    try:
        wired = wire_tools_for_provider(
            provider_name or "",
            tools,
            api_mode=api_mode,
        )
        return wired, None
    except Exception as exc:
        logger.error(
            "wire_tools_for_provider failed; using empty tool list "
            "(provider-specific schema could not be built)",
            exc_info=exc,
        )
        return [], exc


def merge_thinking_headers_safe(
    api_kwargs: dict[str, Any],
    *,
    provider: str,
    model: str,
    label: str = "llm_client.thinking_headers",
) -> dict[str, Any]:
    try:
        from butler.transport.thinking_headers import merge_thinking_request_kwargs

        return cast(
            dict[str, Any],
            merge_thinking_request_kwargs(
                api_kwargs,
                provider=provider,
                model=model,
            ),
        )
    except Exception as exc:
        logger.debug("%s skipped: %s", label, exc)
        return api_kwargs


def iter_stream_safe(
    iterate: Callable[[], str],
    *,
    collected_content: list[str],
) -> str:
    try:
        return iterate()
    except Exception as exc:
        logger.error("Stream error: %s", exc, exc_info=True)
        if not collected_content:
            raise
        return "error"

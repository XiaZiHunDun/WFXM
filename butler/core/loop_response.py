"""Post-LLM response normalization helpers for AgentLoop."""

from __future__ import annotations

from typing import cast

from butler.core.tool_call_normalize import (
    _EMPTY_RETRY_NUDGE,
    _TRUNCATION_NUDGE,
    normalize_tool_calls,
)
from butler.transport.content_sanitize import has_visible_content, strip_think_blocks
from butler.transport.types import NormalizedResponse


def sanitize_response(response: NormalizedResponse) -> NormalizedResponse:
    """Apply content sanitization and tool call normalization."""
    if response.content:
        response.content = strip_think_blocks(response.content) or None
    if response.tool_calls:
        response.tool_calls = normalize_tool_calls(response.tool_calls)
    return response


def needs_empty_content_retry(response: NormalizedResponse) -> bool:
    """True when model returned only reasoning with no tools or visible text."""
    if response.tool_calls:
        return False
    if has_visible_content(response.content):
        return False
    if response.reasoning and str(response.reasoning).strip():
        return True
    return not response.content


def needs_truncation_continue(response: NormalizedResponse) -> bool:
    return response.finish_reason == "length" and not response.tool_calls


def empty_retry_message() -> str:
    return cast(str, _EMPTY_RETRY_NUDGE)


def truncation_continue_message() -> str:
    return cast(str, _TRUNCATION_NUDGE)

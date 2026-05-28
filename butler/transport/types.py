"""Normalized types for LLM transport responses.

Zero external dependencies — pure dataclasses + stdlib.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

@dataclass
class ToolCall:
    id: Optional[str]
    name: str
    arguments: str
    provider_data: Optional[Dict[str, Any]] = None

    @property
    def type(self) -> str:
        return "function"

    @property
    def function(self):
        return self

    def args_dict(self) -> dict:
        try:
            return json.loads(self.arguments)
        except (json.JSONDecodeError, TypeError):
            return {}


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cached_tokens: int = 0


@dataclass
class NormalizedResponse:
    content: Optional[str] = None
    tool_calls: Optional[List[ToolCall]] = None
    finish_reason: str = "stop"
    reasoning: Optional[str] = None
    usage: Optional[Usage] = None
    provider_data: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        self._extract_inline_thinking()


    def _extract_inline_thinking(self):
        """Extract thinking blocks into reasoning; strip leaked tags from content."""
        from butler.transport.content_sanitize import extract_thinking_to_reasoning

        if not self.content:
            return
        visible, reasoning = extract_thinking_to_reasoning(self.content, self.reasoning)
        self.content = visible
        self.reasoning = reasoning


def build_tool_call(
    id: Optional[str],
    name: str,
    arguments: Any,
    **provider_fields,
) -> ToolCall:
    if isinstance(arguments, dict):
        args_str = json.dumps(arguments, ensure_ascii=False)
    else:
        args_str = str(arguments) if arguments is not None else "{}"
    return ToolCall(
        id=id,
        name=name,
        arguments=args_str,
        provider_data=provider_fields or None,
    )


def map_finish_reason(
    reason: Optional[str],
    mapping: Optional[Dict[str, str]] = None,
) -> str:
    if reason is None:
        return "stop"
    if mapping and reason in mapping:
        return mapping[reason]
    return reason

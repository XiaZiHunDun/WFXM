"""Anthropic Messages transport — for Anthropic and MiniMax APIs.

Handles the Anthropic message format where system prompt is a
top-level parameter and tool results use content blocks.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from butler.transport.base import ProviderTransport
from butler.transport.types import NormalizedResponse, ToolCall, Usage

logger = logging.getLogger(__name__)

_STOP_REASON_MAP = {
    "end_turn": "stop",
    "tool_use": "tool_calls",
    "max_tokens": "length",
    "model_context_window_exceeded": "length",
    "stop_sequence": "stop",
    "refusal": "content_filter",
}


def _convert_messages_to_anthropic(
    messages: List[Dict[str, Any]],
) -> tuple[str, List[Dict[str, Any]]]:
    """Convert OpenAI-format messages to Anthropic format.

    Returns (system_prompt, anthropic_messages).
    """
    system_parts: list[str] = []
    anthropic_msgs: list[dict] = []

    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")

        if role == "system":
            if content:
                system_parts.append(content)
            continue

        if role == "assistant":
            blocks: list[Any] = []
            if content:
                blocks.append({"type": "text", "text": content})

            tool_calls = msg.get("tool_calls")
            if tool_calls:
                for tc in tool_calls:
                    fn = tc.get("function", tc)
                    args_str = fn.get("arguments", "{}")
                    try:
                        args = json.loads(args_str) if isinstance(args_str, str) else args_str
                    except json.JSONDecodeError:
                        args = {"raw": args_str}
                    blocks.append({
                        "type": "tool_use",
                        "id": tc.get("id", ""),
                        "name": fn.get("name", ""),
                        "input": args,
                    })

            if blocks:
                anthropic_msgs.append({"role": "assistant", "content": blocks})
            continue

        if role == "tool":
            tool_call_id = msg.get("tool_call_id", "")
            anthropic_msgs.append({
                "role": "user",
                "content": [{
                    "type": "tool_result",
                    "tool_use_id": tool_call_id,
                    "content": str(content) if content else "",
                }],
            })
            continue

        anthropic_msgs.append({"role": "user", "content": str(content) if content else ""})

    return "\n\n".join(system_parts), anthropic_msgs


def _convert_tools_to_anthropic(
    tools: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Convert OpenAI function-calling tools to Anthropic tool format."""
    from butler.transport.schema_sanitizer import sanitize_tool_schemas

    tools = sanitize_tool_schemas(tools, keep_nullable_hint=False) or []
    result = []
    for tool in tools:
        fn = tool.get("function", tool)
        entry = {
            "name": fn.get("name", ""),
            "description": fn.get("description", ""),
            "input_schema": fn.get("parameters", {"type": "object", "properties": {}}),
        }
        result.append(entry)
    return result


class AnthropicTransport(ProviderTransport):

    @property
    def api_mode(self) -> str:
        return "anthropic_messages"

    def convert_messages(
        self, messages: List[Dict[str, Any]], **kwargs
    ) -> tuple[str, List[Dict[str, Any]]]:
        return _convert_messages_to_anthropic(messages)

    def convert_tools(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return _convert_tools_to_anthropic(tools)

    def build_kwargs(
        self,
        model: str,
        messages: Any,
        tools: Optional[Any] = None,
        **params,
    ) -> Dict[str, Any]:
        if isinstance(messages, tuple) and len(messages) == 2:
            system_prompt, anthropic_messages = messages
        else:
            system_prompt, anthropic_messages = _convert_messages_to_anthropic(
                messages if isinstance(messages, list) else []
            )

        kwargs: Dict[str, Any] = {
            "model": model,
            "messages": anthropic_messages,
            "max_tokens": params.get("max_tokens", 4096),
        }

        if system_prompt:
            kwargs["system"] = system_prompt

        if tools:
            if isinstance(tools, list) and tools and "input_schema" not in tools[0]:
                tools = _convert_tools_to_anthropic(tools)
            kwargs["tools"] = tools

        temperature = params.get("temperature")
        if temperature is not None:
            kwargs["temperature"] = temperature

        timeout = params.get("timeout")
        if timeout is not None:
            kwargs["timeout"] = timeout

        stream = params.get("stream")
        if stream is not None:
            kwargs["stream"] = stream

        return kwargs

    def normalize_response(
        self, response: Any, **kwargs
    ) -> NormalizedResponse:
        if isinstance(response, dict):
            return self._normalize_dict(response)
        return self._normalize_sdk(response)

    def _normalize_dict(self, data: dict) -> NormalizedResponse:
        content_blocks = data.get("content", [])
        stop_reason = data.get("stop_reason", "end_turn")

        text_parts: list[str] = []
        reasoning_parts: list[str] = []
        tool_calls: list[ToolCall] = []

        for block in content_blocks:
            btype = block.get("type", "")
            if btype == "text":
                text_parts.append(block.get("text", ""))
            elif btype == "thinking":
                reasoning_parts.append(block.get("thinking", ""))
            elif btype == "tool_use":
                args = block.get("input", {})
                tool_calls.append(ToolCall(
                    id=block.get("id"),
                    name=block.get("name", ""),
                    arguments=json.dumps(args, ensure_ascii=False) if isinstance(args, dict) else str(args),
                ))

        usage = None
        raw_usage = data.get("usage")
        if raw_usage:
            usage = Usage(
                prompt_tokens=raw_usage.get("input_tokens", 0),
                completion_tokens=raw_usage.get("output_tokens", 0),
                total_tokens=raw_usage.get("input_tokens", 0) + raw_usage.get("output_tokens", 0),
            )

        return NormalizedResponse(
            content="\n".join(text_parts) if text_parts else None,
            tool_calls=tool_calls or None,
            finish_reason=_STOP_REASON_MAP.get(stop_reason, "stop"),
            reasoning="\n".join(reasoning_parts) if reasoning_parts else None,
            usage=usage,
        )

    def _normalize_sdk(self, response: Any) -> NormalizedResponse:
        content_blocks = getattr(response, "content", []) or []
        stop_reason = getattr(response, "stop_reason", "end_turn")

        text_parts: list[str] = []
        reasoning_parts: list[str] = []
        tool_calls: list[ToolCall] = []

        for block in content_blocks:
            btype = getattr(block, "type", "")
            if btype == "text":
                text_parts.append(getattr(block, "text", ""))
            elif btype == "thinking":
                thinking = getattr(block, "thinking", "")
                reasoning_parts.append(thinking)
            elif btype == "tool_use":
                args = getattr(block, "input", {})
                tool_calls.append(ToolCall(
                    id=getattr(block, "id", None),
                    name=getattr(block, "name", ""),
                    arguments=json.dumps(args, ensure_ascii=False) if isinstance(args, dict) else str(args),
                ))

        usage = None
        raw_usage = getattr(response, "usage", None)
        if raw_usage:
            usage = Usage(
                prompt_tokens=getattr(raw_usage, "input_tokens", 0),
                completion_tokens=getattr(raw_usage, "output_tokens", 0),
                total_tokens=getattr(raw_usage, "input_tokens", 0) + getattr(raw_usage, "output_tokens", 0),
            )

        return NormalizedResponse(
            content="\n".join(text_parts) if text_parts else None,
            tool_calls=tool_calls or None,
            finish_reason=_STOP_REASON_MAP.get(stop_reason, "stop"),
            reasoning="\n".join(reasoning_parts) if reasoning_parts else None,
            usage=usage,
        )

    def validate_response(self, response: Any) -> bool:
        if isinstance(response, dict):
            return bool(response.get("content")) or response.get("stop_reason") == "end_turn"
        content = getattr(response, "content", None)
        return bool(content) or getattr(response, "stop_reason", None) == "end_turn"


from butler.transport import register_transport  # noqa: E402
register_transport("anthropic_messages", AnthropicTransport)

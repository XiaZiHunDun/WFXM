"""Anthropic Claude provider."""

from __future__ import annotations

import json
import uuid
from typing import Any, AsyncIterator

import anthropic

from butler.providers.base import (
    CompletionResult,
    LLMProvider,
    Message,
    Role,
    StreamDelta,
    ToolCall,
)


class ClaudeProvider(LLMProvider):
    name = "claude"

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514", **kwargs: Any):
        self.model = model
        self.client = anthropic.AsyncAnthropic(api_key=api_key)

    def _convert_messages(self, messages: list[Message]) -> tuple[str, list[dict]]:
        system = ""
        converted: list[dict] = []
        for msg in messages:
            if msg.role == Role.SYSTEM:
                system = msg.content
                continue
            if msg.role == Role.USER:
                converted.append({"role": "user", "content": msg.content})
            elif msg.role == Role.ASSISTANT:
                content: list[dict] = []
                if msg.content:
                    content.append({"type": "text", "text": msg.content})
                if msg.tool_calls:
                    for tc in msg.tool_calls:
                        content.append({
                            "type": "tool_use",
                            "id": tc.id,
                            "name": tc.name,
                            "input": tc.arguments,
                        })
                converted.append({"role": "assistant", "content": content or msg.content})
            elif msg.role == Role.TOOL:
                if msg.tool_results:
                    tool_results = []
                    for tr in msg.tool_results:
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": tr.tool_call_id,
                            "content": tr.content,
                            "is_error": tr.is_error,
                        })
                    converted.append({"role": "user", "content": tool_results})
        return system, converted

    def _convert_tools(self, tools: list[dict[str, Any]] | None) -> list[dict] | None:
        if not tools:
            return None
        anthropic_tools = []
        for tool in tools:
            fn = tool.get("function", tool)
            anthropic_tools.append({
                "name": fn["name"],
                "description": fn.get("description", ""),
                "input_schema": fn.get("parameters", {"type": "object", "properties": {}}),
            })
        return anthropic_tools

    async def complete(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> CompletionResult:
        system, converted = self._convert_messages(messages)
        api_tools = self._convert_tools(tools)

        params: dict[str, Any] = {
            "model": model or self.model,
            "messages": converted,
            "max_tokens": max_tokens or 8192,
        }
        if system:
            params["system"] = system
        if api_tools:
            params["tools"] = api_tools
        if temperature is not None:
            params["temperature"] = temperature

        response = await self.client.messages.create(**params)

        text_parts = []
        tool_calls = []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(ToolCall(
                    id=block.id,
                    name=block.name,
                    arguments=block.input if isinstance(block.input, dict) else json.loads(block.input),
                ))

        return CompletionResult(
            message=Message.assistant("\n".join(text_parts), tool_calls=tool_calls or None),
            usage={
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            },
            model=response.model,
            finish_reason=response.stop_reason or "",
        )

    async def stream(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[StreamDelta]:
        system, converted = self._convert_messages(messages)
        api_tools = self._convert_tools(tools)

        params: dict[str, Any] = {
            "model": model or self.model,
            "messages": converted,
            "max_tokens": max_tokens or 8192,
        }
        if system:
            params["system"] = system
        if api_tools:
            params["tools"] = api_tools
        if temperature is not None:
            params["temperature"] = temperature

        current_tool_id = ""
        current_tool_name = ""
        current_tool_json = ""

        async with self.client.messages.stream(**params) as stream:
            async for event in stream:
                if event.type == "content_block_start":
                    if hasattr(event.content_block, "type") and event.content_block.type == "tool_use":
                        current_tool_id = event.content_block.id
                        current_tool_name = event.content_block.name
                        current_tool_json = ""
                elif event.type == "content_block_delta":
                    if hasattr(event.delta, "text"):
                        yield StreamDelta(text=event.delta.text)
                    elif hasattr(event.delta, "partial_json"):
                        current_tool_json += event.delta.partial_json
                elif event.type == "content_block_stop":
                    if current_tool_name:
                        try:
                            args = json.loads(current_tool_json) if current_tool_json else {}
                        except json.JSONDecodeError:
                            args = {}
                        yield StreamDelta(tool_call=ToolCall(
                            id=current_tool_id,
                            name=current_tool_name,
                            arguments=args,
                        ))
                        current_tool_id = ""
                        current_tool_name = ""
                        current_tool_json = ""
                elif event.type == "message_stop":
                    yield StreamDelta(finish_reason="stop")

    async def close(self):
        await self.client.close()

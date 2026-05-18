"""OpenAI-compatible provider (OpenAI, DeepSeek, etc.)."""

from __future__ import annotations

import json
from typing import Any, AsyncIterator

import openai

from butler.providers.base import (
    CompletionResult,
    LLMProvider,
    Message,
    Role,
    StreamDelta,
    ToolCall,
)


class OpenAIProvider(LLMProvider):
    name = "openai"

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o",
        base_url: str | None = None,
        **kwargs: Any,
    ):
        self.model = model
        self.client = openai.AsyncOpenAI(api_key=api_key, base_url=base_url)

    def _convert_messages(self, messages: list[Message]) -> list[dict]:
        converted: list[dict] = []
        for msg in messages:
            if msg.role == Role.SYSTEM:
                converted.append({"role": "system", "content": msg.content})
            elif msg.role == Role.USER:
                converted.append({"role": "user", "content": msg.content})
            elif msg.role == Role.ASSISTANT:
                entry: dict[str, Any] = {"role": "assistant"}
                if msg.content:
                    entry["content"] = msg.content
                if msg.tool_calls:
                    entry["tool_calls"] = [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)},
                        }
                        for tc in msg.tool_calls
                    ]
                converted.append(entry)
            elif msg.role == Role.TOOL and msg.tool_results:
                for tr in msg.tool_results:
                    converted.append({
                        "role": "tool",
                        "tool_call_id": tr.tool_call_id,
                        "content": tr.content,
                    })
        return converted

    def _convert_tools(self, tools: list[dict[str, Any]] | None) -> list[dict] | None:
        if not tools:
            return None
        oai_tools = []
        for tool in tools:
            if "function" in tool:
                oai_tools.append(tool)
            else:
                oai_tools.append({
                    "type": "function",
                    "function": {
                        "name": tool["name"],
                        "description": tool.get("description", ""),
                        "parameters": tool.get("parameters", {"type": "object", "properties": {}}),
                    },
                })
        return oai_tools

    async def complete(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> CompletionResult:
        converted = self._convert_messages(messages)
        api_tools = self._convert_tools(tools)

        params: dict[str, Any] = {
            "model": model or self.model,
            "messages": converted,
        }
        if api_tools:
            params["tools"] = api_tools
        if temperature is not None:
            params["temperature"] = temperature
        if max_tokens:
            params["max_tokens"] = max_tokens

        response = await self.client.chat.completions.create(**params)
        choice = response.choices[0]

        tool_calls = None
        if choice.message.tool_calls:
            tool_calls = [
                ToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=json.loads(tc.function.arguments) if tc.function.arguments else {},
                )
                for tc in choice.message.tool_calls
            ]

        return CompletionResult(
            message=Message.assistant(choice.message.content or "", tool_calls=tool_calls),
            usage={
                "input_tokens": response.usage.prompt_tokens if response.usage else 0,
                "output_tokens": response.usage.completion_tokens if response.usage else 0,
            },
            model=response.model,
            finish_reason=choice.finish_reason or "",
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
        converted = self._convert_messages(messages)
        api_tools = self._convert_tools(tools)

        params: dict[str, Any] = {
            "model": model or self.model,
            "messages": converted,
            "stream": True,
        }
        if api_tools:
            params["tools"] = api_tools
        if temperature is not None:
            params["temperature"] = temperature
        if max_tokens:
            params["max_tokens"] = max_tokens

        tool_buffers: dict[int, dict] = {}

        response = await self.client.chat.completions.create(**params)
        async for chunk in response:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta

            if delta.content:
                yield StreamDelta(text=delta.content)

            if delta.tool_calls:
                for tc_delta in delta.tool_calls:
                    idx = tc_delta.index
                    if idx not in tool_buffers:
                        tool_buffers[idx] = {"id": "", "name": "", "arguments": ""}
                    buf = tool_buffers[idx]
                    if tc_delta.id:
                        buf["id"] = tc_delta.id
                    if tc_delta.function:
                        if tc_delta.function.name:
                            buf["name"] = tc_delta.function.name
                        if tc_delta.function.arguments:
                            buf["arguments"] += tc_delta.function.arguments

            if chunk.choices[0].finish_reason:
                for buf in tool_buffers.values():
                    if buf["name"]:
                        try:
                            args = json.loads(buf["arguments"]) if buf["arguments"] else {}
                        except json.JSONDecodeError:
                            args = {}
                        yield StreamDelta(tool_call=ToolCall(id=buf["id"], name=buf["name"], arguments=args))
                tool_buffers.clear()
                yield StreamDelta(finish_reason=chunk.choices[0].finish_reason)

    async def close(self):
        await self.client.close()

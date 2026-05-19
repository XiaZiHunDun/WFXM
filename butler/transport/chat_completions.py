"""Chat Completions transport — OpenAI-compatible API format.

Handles request building and response normalization for any provider
that speaks the OpenAI chat completions protocol (DeepSeek, Qwen,
OpenAI, local models, etc.).
"""

from __future__ import annotations

import copy
import logging
from typing import Any, Dict, List, Optional

from butler.transport.base import ProviderTransport
from butler.transport.types import NormalizedResponse, ToolCall, Usage

logger = logging.getLogger(__name__)


class ChatCompletionsTransport(ProviderTransport):

    @property
    def api_mode(self) -> str:
        return "chat_completions"

    def convert_messages(
        self, messages: List[Dict[str, Any]], **kwargs
    ) -> List[Dict[str, Any]]:
        from butler.transport.reasoning_replay import apply_reasoning_for_api

        provider = kwargs.get("provider", "")
        model = kwargs.get("model", "")
        base_url = kwargs.get("base_url")

        result = []
        for msg in messages:
            m = dict(msg)
            m.pop("codex_reasoning_items", None)
            m.pop("codex_message_items", None)
            if "tool_calls" in m and isinstance(m["tool_calls"], list):
                cleaned = []
                for tc in m["tool_calls"]:
                    if isinstance(tc, dict):
                        tc = {k: v for k, v in tc.items()
                              if k not in ("call_id", "response_item_id", "extra_content")}
                    cleaned.append(tc)
                m["tool_calls"] = cleaned
            apply_reasoning_for_api(
                msg, m, provider=provider, model=model, base_url=base_url,
            )
            # ``reasoning`` is Butler's internal normalized field; providers
            # that need it receive ``reasoning_content`` instead.
            m.pop("reasoning", None)
            result.append(m)
        return result

    def build_kwargs(
        self,
        model: str,
        messages: Any,
        tools: Optional[Any] = None,
        **params,
    ) -> Dict[str, Any]:
        provider = params.pop("provider", "")
        base_url = params.pop("base_url", None)
        sanitized = self.convert_messages(
            messages,
            provider=provider,
            model=model,
            base_url=base_url,
        )

        kwargs: Dict[str, Any] = {
            "model": model,
            "messages": sanitized,
        }

        if tools:
            kwargs["tools"] = tools

        temperature = params.get("temperature")
        if temperature is not None:
            kwargs["temperature"] = temperature

        max_tokens = params.get("max_tokens")
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens

        timeout = params.get("timeout")
        if timeout is not None:
            kwargs["timeout"] = timeout

        stream = params.get("stream")
        if stream is not None:
            kwargs["stream"] = stream

        extra_body = params.get("extra_body")
        if extra_body and isinstance(extra_body, dict):
            kwargs["extra_body"] = extra_body

        return kwargs

    def normalize_response(
        self, response: Any, **kwargs
    ) -> NormalizedResponse:
        if isinstance(response, dict):
            return self._normalize_dict(response)
        return self._normalize_sdk(response)

    def _normalize_dict(self, data: dict) -> NormalizedResponse:
        choices = data.get("choices", [])
        if not choices:
            return NormalizedResponse(finish_reason="error")

        choice = choices[0]
        msg = choice.get("message", {})
        finish = choice.get("finish_reason") or "stop"

        content = msg.get("content")
        reasoning = msg.get("reasoning") or msg.get("reasoning_content")

        tool_calls = None
        raw_tcs = msg.get("tool_calls")
        if raw_tcs:
            tool_calls = []
            for tc in raw_tcs:
                fn = tc.get("function", {})
                tool_calls.append(ToolCall(
                    id=tc.get("id"),
                    name=fn.get("name", ""),
                    arguments=fn.get("arguments", "{}"),
                ))

        usage = None
        raw_usage = data.get("usage")
        if raw_usage:
            usage = Usage(
                prompt_tokens=raw_usage.get("prompt_tokens", 0),
                completion_tokens=raw_usage.get("completion_tokens", 0),
                total_tokens=raw_usage.get("total_tokens", 0),
            )

        return NormalizedResponse(
            content=content,
            tool_calls=tool_calls,
            finish_reason=finish,
            reasoning=reasoning,
            usage=usage,
        )

    def _normalize_sdk(self, response: Any) -> NormalizedResponse:
        """Normalize an OpenAI SDK response object."""
        choices = getattr(response, "choices", None) or []
        if not choices:
            return NormalizedResponse(finish_reason="error")

        choice = choices[0]
        msg = getattr(choice, "message", None)
        finish = getattr(choice, "finish_reason", None) or "stop"

        content = getattr(msg, "content", None) if msg else None
        reasoning = getattr(msg, "reasoning", None) or getattr(msg, "reasoning_content", None)

        tool_calls = None
        raw_tcs = getattr(msg, "tool_calls", None) if msg else None
        if raw_tcs:
            tool_calls = []
            for tc in raw_tcs:
                fn = getattr(tc, "function", None)
                tool_calls.append(ToolCall(
                    id=getattr(tc, "id", None),
                    name=getattr(fn, "name", "") if fn else "",
                    arguments=getattr(fn, "arguments", "{}") if fn else "{}",
                ))

        usage = None
        raw_usage = getattr(response, "usage", None)
        if raw_usage:
            usage = Usage(
                prompt_tokens=getattr(raw_usage, "prompt_tokens", 0),
                completion_tokens=getattr(raw_usage, "completion_tokens", 0),
                total_tokens=getattr(raw_usage, "total_tokens", 0),
            )

        return NormalizedResponse(
            content=content,
            tool_calls=tool_calls,
            finish_reason=finish,
            reasoning=reasoning,
            usage=usage,
        )

    def validate_response(self, response: Any) -> bool:
        if isinstance(response, dict):
            return bool(response.get("choices"))
        return bool(getattr(response, "choices", None))


from butler.transport import register_transport
register_transport("chat_completions", ChatCompletionsTransport)

"""LLM HTTP Client — handles actual API calls.

Supports both OpenAI SDK and raw httpx for flexibility.
Provides both streaming and non-streaming call modes.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from butler.transport.types import NormalizedResponse, Usage
from butler.transport.providers import ProviderProfile, get_provider

logger = logging.getLogger(__name__)


class LLMClient:
    """Stateful LLM API client for a specific provider configuration."""

    def __init__(
        self,
        *,
        provider: str = "",
        model: str = "",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        api_mode: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        timeout: int = 120,
    ):
        self.provider_name = provider
        self.model = model
        self._api_key = api_key
        self._base_url = base_url
        self._api_mode = api_mode
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.timeout = timeout

        self._profile: Optional[ProviderProfile] = None
        self._client: Any = None

        self._resolve_config()

    def _resolve_config(self) -> None:
        if self.provider_name:
            self._profile = get_provider(self.provider_name)

        if self._profile:
            if not self._base_url:
                self._base_url = self._profile.base_url
            if not self._api_key:
                self._api_key = self._profile.resolve_api_key()
            if not self._api_mode:
                self._api_mode = self._profile.api_mode
            if not self.model:
                self.model = self._profile.default_model
            if self.max_tokens is None:
                self.max_tokens = self._profile.default_max_tokens

        if not self._api_mode:
            self._api_mode = self._detect_api_mode()

    def _detect_api_mode(self) -> str:
        url = (self._base_url or "").lower().rstrip("/")
        if url.endswith("/anthropic"):
            return "anthropic_messages"
        return "chat_completions"

    @property
    def api_mode(self) -> str:
        return self._api_mode or "chat_completions"

    _MAX_RETRIES = 0  # 重试由外层 llm_retry 中间件统一处理，关闭 SDK 默认重试避免双层放大（Sprint 10 PERF-NEW-3）

    def _get_openai_client(self):
        if self._client is None:
            try:
                from openai import OpenAI
                api_key = self._api_key
                if not api_key:
                    logger.warning("OpenAI client created without API key; calls will likely fail")
                    api_key = "dummy"
                self._client = OpenAI(
                    api_key=api_key,
                    base_url=self._base_url,
                    timeout=self.timeout,
                    max_retries=self._MAX_RETRIES,
                )
            except ImportError:
                raise RuntimeError("openai package required: pip install openai")
        return self._client

    def _get_anthropic_client(self):
        if self._client is None:
            api_key = self._api_key
            if not api_key:
                logger.warning("Anthropic client created without API key; calls will likely fail")
                api_key = "dummy"
            try:
                from anthropic import Anthropic
                self._client = Anthropic(
                    api_key=api_key,
                    base_url=self._base_url,
                    timeout=self.timeout,
                    max_retries=self._MAX_RETRIES,
                )
            except ImportError:
                try:
                    from openai import OpenAI
                    self._client = OpenAI(
                        api_key=api_key,
                        base_url=self._base_url,
                        timeout=self.timeout,
                        max_retries=self._MAX_RETRIES,
                    )
                    self._api_mode = "chat_completions"
                except ImportError:
                    raise RuntimeError("anthropic or openai package required")
        return self._client

    def complete(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        check_interrupt: Optional[Callable[[], bool]] = None,
        stale_timeout: Optional[float] = None,
        **kwargs,
    ) -> NormalizedResponse:
        """Non-streaming completion."""
        from butler.transport import get_transport

        transport = get_transport(self.api_mode)
        if transport is None:
            raise ValueError(f"No transport for api_mode={self.api_mode}")

        converted_tools = None
        if tools:
            try:
                from butler.transport.tool_wire import wire_tools_for_provider

                converted_tools = wire_tools_for_provider(
                    self.provider_name or "",
                    tools,
                    api_mode=self.api_mode,
                )
            except Exception as exc:
                logger.warning("wire_tools_for_provider failed, falling back: %s", exc)
                converted_tools = transport.convert_tools(tools)

        params = {
            "temperature": kwargs.get("temperature", self.temperature),
            "max_tokens": kwargs.get("max_tokens", self.max_tokens),
            "timeout": kwargs.get("timeout", self.timeout),
            "stream": False,
            "provider": self.provider_name,
            "base_url": self._base_url,
        }
        params = {k: v for k, v in params.items() if v is not None}

        api_kwargs = transport.build_kwargs(
            model=self.model,
            messages=messages,
            tools=converted_tools,
            **params,
        )

        from butler.transport.interruptible_client import run_interruptible

        stale = stale_timeout if stale_timeout is not None else min(float(self.timeout or 120), 90.0)

        def _do() -> NormalizedResponse:
            response = self._raw_call(api_kwargs)
            return transport.normalize_response(response)

        return run_interruptible(
            _do,
            check_interrupt=check_interrupt,
            stale_timeout=stale,
        )

    def stream(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        on_delta: Optional[Callable[[str], None]] = None,
        on_tool_call_ready: Optional[Callable[[int, str, str, dict], None]] = None,
        check_interrupt: Optional[Callable[[], bool]] = None,
        stale_timeout: Optional[float] = None,
        **kwargs,
    ) -> NormalizedResponse:
        """Streaming completion with delta callback."""
        from butler.transport import get_transport

        transport = get_transport(self.api_mode)
        if transport is None:
            raise ValueError(f"No transport for api_mode={self.api_mode}")

        converted_tools = None
        if tools:
            try:
                from butler.transport.tool_wire import wire_tools_for_provider

                converted_tools = wire_tools_for_provider(
                    self.provider_name or "",
                    tools,
                    api_mode=self.api_mode,
                )
            except Exception as exc:
                logger.warning("wire_tools_for_provider (stream) failed, falling back: %s", exc)
                converted_tools = transport.convert_tools(tools)

        params = {
            "temperature": kwargs.get("temperature", self.temperature),
            "max_tokens": kwargs.get("max_tokens", self.max_tokens),
            "timeout": kwargs.get("timeout", self.timeout),
            "stream": True,
            "provider": self.provider_name,
            "base_url": self._base_url,
        }
        params = {k: v for k, v in params.items() if v is not None}

        api_kwargs = transport.build_kwargs(
            model=self.model,
            messages=messages,
            tools=converted_tools,
            **params,
        )

        from butler.transport.interruptible_client import run_interruptible
        from butler.transport.think_scrubber import StreamingThinkScrubber

        stale = stale_timeout if stale_timeout is not None else min(float(self.timeout or 120), 90.0)
        scrubber = StreamingThinkScrubber()

        def _wrapped_delta(delta: str) -> None:
            if on_delta:
                visible = scrubber.feed(delta)
                if visible:
                    on_delta(visible)

        def _do() -> NormalizedResponse:
            try:
                return self._stream_call(
                    api_kwargs,
                    on_delta=_wrapped_delta if on_delta else None,
                    on_tool_call_ready=on_tool_call_ready,
                    transport=transport,
                )
            finally:
                if on_delta:
                    tail = scrubber.flush()
                    if tail:
                        on_delta(tail)

        return run_interruptible(
            _do,
            check_interrupt=check_interrupt,
            stale_timeout=stale,
        )

    def _raw_call(self, api_kwargs: dict) -> Any:
        """Execute the actual API call."""
        api_kwargs.pop("stream", None)

        if self.api_mode == "anthropic_messages":
            return self._call_anthropic(api_kwargs)
        return self._call_openai(api_kwargs)

    def _call_openai(self, api_kwargs: dict) -> Any:
        client = self._get_openai_client()
        return client.chat.completions.create(**api_kwargs)

    def _call_anthropic(self, api_kwargs: dict) -> Any:
        try:
            from butler.transport.thinking_headers import merge_thinking_request_kwargs

            api_kwargs = merge_thinking_request_kwargs(
                api_kwargs,
                provider=self.provider_name or "",
                model=self.model or "",
            )
        except Exception as exc:
            logger.debug("Thinking headers merge skipped: %s", exc)
        client = self._get_anthropic_client()
        if hasattr(client, "messages"):
            return client.messages.create(**api_kwargs)
        return client.chat.completions.create(**api_kwargs)

    def _stream_call(
        self,
        api_kwargs: dict,
        on_delta: Optional[Callable[[str], None]] = None,
        on_tool_call_ready: Optional[Callable[[int, str, str, dict], None]] = None,
        transport: Any = None,
    ) -> NormalizedResponse:
        """Execute streaming API call and collect into NormalizedResponse."""
        from butler.transport.types import ToolCall

        api_kwargs["stream"] = True

        collected_content = []
        collected_reasoning = []
        collected_tool_calls: dict[int, dict] = {}
        finish_reason = "stop"
        usage = None

        try:
            if self.api_mode == "anthropic_messages":
                return self._stream_anthropic(
                    api_kwargs,
                    on_delta,
                    transport,
                    on_tool_call_ready=on_tool_call_ready,
                )

            client = self._get_openai_client()
            stream = client.chat.completions.create(**api_kwargs)

            for chunk in stream:
                if not hasattr(chunk, "choices") or not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                fr = chunk.choices[0].finish_reason

                if fr:
                    finish_reason = fr

                text = getattr(delta, "content", None)
                if text:
                    collected_content.append(text)
                    if on_delta:
                        on_delta(text)

                reasoning = getattr(delta, "reasoning_content", None) or getattr(delta, "reasoning", None)
                if isinstance(reasoning, str) and reasoning:
                    collected_reasoning.append(reasoning)

                tcs = getattr(delta, "tool_calls", None)
                if tcs:
                    for tc in tcs:
                        idx = getattr(tc, "index", 0)
                        if idx not in collected_tool_calls:
                            collected_tool_calls[idx] = {
                                "id": getattr(tc, "id", None),
                                "name": "",
                                "arguments": "",
                            }
                        entry = collected_tool_calls[idx]
                        if getattr(tc, "id", None):
                            entry["id"] = tc.id
                        fn = getattr(tc, "function", None)
                        if fn:
                            if getattr(fn, "name", None):
                                entry["name"] = fn.name
                            if getattr(fn, "arguments", None):
                                entry["arguments"] += fn.arguments
                    from butler.transport.streaming_signal import (
                        notify_complete_tool_calls_from_stream,
                    )

                    notify_complete_tool_calls_from_stream(
                        collected_tool_calls,
                        on_tool_call_ready,
                    )

                raw_usage = getattr(chunk, "usage", None)
                if raw_usage:
                    usage = Usage(
                        prompt_tokens=getattr(raw_usage, "prompt_tokens", 0),
                        completion_tokens=getattr(raw_usage, "completion_tokens", 0),
                        total_tokens=getattr(raw_usage, "total_tokens", 0),
                    )

        except Exception as exc:
            logger.error("Stream error: %s", exc, exc_info=True)
            if not collected_content:
                raise
            finish_reason = "error"

        from butler.transport.streaming_signal import notify_complete_tool_calls_from_stream

        notify_complete_tool_calls_from_stream(
            collected_tool_calls,
            on_tool_call_ready,
        )

        tool_calls = None
        if collected_tool_calls:
            tool_calls = []
            for idx in sorted(collected_tool_calls.keys()):
                tc = collected_tool_calls[idx]
                tool_calls.append(ToolCall(
                    id=tc["id"],
                    name=tc["name"],
                    arguments=tc["arguments"] or "{}",
                ))

        return NormalizedResponse(
            content="".join(collected_content) or None,
            tool_calls=tool_calls or None,
            finish_reason=finish_reason,
            reasoning="".join(collected_reasoning) or None,
            usage=usage,
        )

    def _stream_anthropic(
        self,
        api_kwargs: dict,
        on_delta: Optional[Callable[[str], None]],
        transport: Any,
        on_tool_call_ready: Optional[Callable[[int, str, str, dict], None]] = None,
    ) -> NormalizedResponse:
        from butler.transport.types import ToolCall

        api_kwargs.pop("stream", None)
        try:
            from butler.transport.thinking_headers import merge_thinking_request_kwargs

            api_kwargs = merge_thinking_request_kwargs(
                api_kwargs,
                provider=self.provider_name or "",
                model=self.model or "",
            )
        except Exception as exc:
            logger.debug("Thinking headers merge skipped (stream): %s", exc)

        client = self._get_anthropic_client()
        if not hasattr(client, "messages"):
            api_kwargs["stream"] = True
            return self._stream_call(
                api_kwargs,
                on_delta=on_delta,
                transport=transport,
                on_tool_call_ready=on_tool_call_ready,
            )

        collected_text: list[str] = []
        tool_calls: list[ToolCall] = []
        current_tool: Optional[dict] = None
        finish_reason = "stop"
        usage = None

        with client.messages.stream(**api_kwargs) as stream:
            for event in stream:
                etype = getattr(event, "type", "")

                if etype == "content_block_start":
                    block = getattr(event, "content_block", None)
                    if block and getattr(block, "type", "") == "tool_use":
                        current_tool = {
                            "id": getattr(block, "id", None),
                            "name": getattr(block, "name", ""),
                            "arguments": "",
                        }

                elif etype == "content_block_delta":
                    delta = getattr(event, "delta", None)
                    if delta:
                        dtype = getattr(delta, "type", "")
                        if dtype == "text_delta":
                            text = getattr(delta, "text", "")
                            if text:
                                collected_text.append(text)
                                if on_delta:
                                    on_delta(text)
                        elif dtype == "input_json_delta" and current_tool:
                            partial = getattr(delta, "partial_json", "")
                            if partial:
                                current_tool["arguments"] += partial

                elif etype == "content_block_stop":
                    if current_tool:
                        from butler.transport.streaming_signal import (
                            notify_complete_tool_calls_from_stream,
                        )

                        notify_complete_tool_calls_from_stream(
                            {len(tool_calls): current_tool},
                            on_tool_call_ready,
                        )
                        tool_calls.append(ToolCall(
                            id=current_tool["id"],
                            name=current_tool["name"],
                            arguments=current_tool["arguments"] or "{}",
                        ))
                        current_tool = None

                elif etype == "message_delta":
                    delta = getattr(event, "delta", None)
                    if delta:
                        sr = getattr(delta, "stop_reason", None)
                        if sr:
                            from butler.transport.anthropic_transport import _STOP_REASON_MAP
                            finish_reason = _STOP_REASON_MAP.get(sr, "stop")
                    raw_usage = getattr(event, "usage", None)
                    if raw_usage:
                        usage = Usage(
                            prompt_tokens=getattr(raw_usage, "input_tokens", 0),
                            completion_tokens=getattr(raw_usage, "output_tokens", 0),
                            total_tokens=getattr(raw_usage, "input_tokens", 0) + getattr(raw_usage, "output_tokens", 0),
                        )

        return NormalizedResponse(
            content="".join(collected_text) or None,
            tool_calls=tool_calls or None,
            finish_reason=finish_reason,
            usage=usage,
        )

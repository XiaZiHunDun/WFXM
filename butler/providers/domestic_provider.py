"""Domestic (Chinese) LLM providers - Qwen, GLM, Moonshot, MiniMax, etc.

All expose OpenAI-compatible APIs, so we reuse OpenAIProvider with custom defaults.
Adds handling for <think> reasoning tokens that some models emit.
"""

from __future__ import annotations

import re
from typing import Any, AsyncIterator

from butler.providers.base import CompletionResult, Message, StreamDelta
from butler.providers.openai_provider import OpenAIProvider

_DOMESTIC_PROVIDERS = {
    "qwen": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-max",
        "env_key": "DASHSCOPE_API_KEY",
    },
    "glm": {
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "model": "glm-4-plus",
        "env_key": "ZHIPUAI_API_KEY",
    },
    "moonshot": {
        "base_url": "https://api.moonshot.cn/v1",
        "model": "moonshot-v1-auto",
        "env_key": "MOONSHOT_API_KEY",
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-chat",
        "env_key": "DEEPSEEK_API_KEY",
    },
    "doubao": {
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "model": "doubao-pro-256k",
        "env_key": "ARK_API_KEY",
    },
    "minimax": {
        "base_url": "https://api.minimax.chat/v1",
        "model": "MiniMax-M2.7",
        "env_key": "MINIMAX_API_KEY",
    },
}

_THINK_RE = re.compile(r"<think>.*?</think>\s*", re.DOTALL)
_THINK_OPEN_RE = re.compile(r"<think>.*", re.DOTALL)


def _strip_think_tags(text: str) -> str:
    """Remove <think>...</think> reasoning blocks from model output."""
    if "<think>" not in text:
        return text
    result = _THINK_RE.sub("", text)
    result = _THINK_OPEN_RE.sub("", result)
    return result.strip()


class DomesticProvider(OpenAIProvider):
    """Wrapper for Chinese LLM providers that use OpenAI-compatible APIs.

    Adds automatic stripping of <think> reasoning tags from responses.
    """

    def __init__(self, provider_name: str, api_key: str, model: str = "", base_url: str = "", **kwargs: Any):
        config = _DOMESTIC_PROVIDERS.get(provider_name, {})
        super().__init__(
            api_key=api_key,
            model=model or config.get("model", ""),
            base_url=base_url or config.get("base_url"),
        )
        self.name = provider_name

    async def complete(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> CompletionResult:
        result = await super().complete(
            messages, tools=tools, model=model,
            temperature=temperature, max_tokens=max_tokens, **kwargs,
        )
        if result.message.content:
            result.message.content = _strip_think_tags(result.message.content)
        return result

    async def stream(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[StreamDelta]:
        in_think = False
        async for delta in super().stream(
            messages, tools=tools, model=model,
            temperature=temperature, max_tokens=max_tokens, **kwargs,
        ):
            if delta.text:
                text = delta.text
                if "<think>" in text:
                    in_think = True
                    text = text[:text.index("<think>")]
                if in_think:
                    if "</think>" in delta.text:
                        in_think = False
                        after_close = delta.text[delta.text.index("</think>") + 8:]
                        if after_close.strip():
                            yield StreamDelta(text=after_close)
                    elif text:
                        yield StreamDelta(text=text)
                    continue
                yield StreamDelta(text=text)
            elif delta.tool_call or delta.finish_reason:
                yield delta


def get_domestic_config(provider_name: str) -> dict[str, str]:
    return _DOMESTIC_PROVIDERS.get(provider_name, {})


def list_domestic_providers() -> list[str]:
    return list(_DOMESTIC_PROVIDERS.keys())

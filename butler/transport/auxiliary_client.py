"""Cheap-model router for side tasks (compression, post-session extraction)."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from butler.config import ModelConfig, get_butler_settings
from butler.transport.llm_client import LLMClient

logger = logging.getLogger(__name__)


def resolve_auxiliary_config(task: str = "compression") -> ModelConfig:
    """Pick auxiliary model: ``config.yaml`` auxiliary.* → **default_provider** (MiniMax) → butler model."""
    settings = get_butler_settings()
    cfg = settings.get_auxiliary_task_config(task)
    if not cfg.is_empty():
        return cfg

    preferred = (settings.default_provider or "minimax").strip()
    if preferred and (pc := settings.providers.get(preferred)):
        return ModelConfig(provider=preferred, model=pc.model or "")

    from butler.model_resolve import resolve_effective_model

    butler_cfg = resolve_effective_model("butler", settings=settings).config
    if not butler_cfg.is_empty():
        return butler_cfg

    from butler.defaults.model_defaults import AUXILIARY_SCAN_PROVIDERS

    for name in AUXILIARY_SCAN_PROVIDERS:
        if (pc := settings.providers.get(name)):
            return ModelConfig(provider=name, model=pc.model or "")
    return ModelConfig(provider=preferred or "minimax", model="")


def create_auxiliary_client(task: str = "compression", **kwargs: Any) -> LLMClient:
    cfg = resolve_auxiliary_config(task)
    settings = get_butler_settings()
    pc = settings.providers.get(cfg.provider) if cfg.provider else None
    return LLMClient(
        provider=cfg.provider,
        model=cfg.model or (pc.model if pc else ""),
        api_key=pc.api_key if pc else None,
        base_url=pc.base_url if pc else None,
        max_tokens=cfg.max_tokens or 4096,
        temperature=cfg.temperature if cfg.temperature is not None else 0.3,
        **kwargs,
    )


def auxiliary_complete(
    prompt: str,
    *,
    task: str = "compression",
    system: str = "You are a concise assistant.",
    session_key: str = "",
) -> str:
    """Single-shot completion for side tasks."""
    client = create_auxiliary_client(task)
    resp = client.complete(
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
    )
    sk = session_key or _current_session_key()
    if sk and resp.usage:
        from butler.transport.auxiliary_client_ops import record_auxiliary_llm_cost_safe

        record_auxiliary_llm_cost_safe(sk, resp.usage)
    return resp.content or ""


def _current_session_key() -> str:
    from butler.transport.auxiliary_client_ops import current_auxiliary_session_key_safe

    return current_auxiliary_session_key_safe()


def auxiliary_llm_call_factory(
    task: str = "post_session",
) -> Callable[[str], Awaitable[str]]:
    """Async callable for PostSessionProcessor (blocking HTTP runs in a thread)."""

    async def _call(prompt: str) -> str:
        return await asyncio.to_thread(auxiliary_complete, prompt, task=task)

    return _call

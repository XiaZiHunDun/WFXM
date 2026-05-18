"""Provider registry - maps provider names to LLMProvider instances."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from butler.config.settings import ModelConfig, settings

if TYPE_CHECKING:
    from butler.providers.base import LLMProvider

logger = logging.getLogger(__name__)

_providers: dict[str, LLMProvider] = {}

_DOMESTIC_NAMES = {"qwen", "glm", "moonshot", "deepseek", "doubao", "minimax"}


def register_provider(name: str, provider: LLMProvider) -> None:
    _providers[name] = provider


def get_provider(name: str | None = None) -> LLMProvider:
    name = name or settings.default_provider

    if name in _providers:
        return _providers[name]

    if name not in settings.providers:
        available = list(settings.providers.keys()) or ["(none configured)"]
        raise ValueError(f"Provider '{name}' not configured. Available: {', '.join(available)}")

    cfg = settings.providers[name]
    provider = _create_provider(name, cfg)
    _providers[name] = provider
    return provider


def get_provider_for_model(model_config: ModelConfig) -> LLMProvider:
    """Get a provider instance configured for a specific ModelConfig."""
    provider_name = model_config.provider or settings.default_provider
    provider = get_provider(provider_name)
    return provider


def _create_provider(name: str, cfg) -> LLMProvider:
    if name == "claude":
        from butler.providers.claude_provider import ClaudeProvider
        return ClaudeProvider(api_key=cfg.api_key, model=cfg.model)
    elif name in _DOMESTIC_NAMES:
        from butler.providers.domestic_provider import DomesticProvider
        return DomesticProvider(
            provider_name=name, api_key=cfg.api_key,
            model=cfg.model, base_url=cfg.base_url,
        )
    else:
        from butler.providers.openai_provider import OpenAIProvider
        return OpenAIProvider(
            api_key=cfg.api_key, model=cfg.model,
            base_url=cfg.base_url or None,
        )


def list_providers() -> list[str]:
    return list(settings.providers.keys())

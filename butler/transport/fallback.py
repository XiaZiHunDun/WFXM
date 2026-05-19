"""LLM provider fallback chain for Butler."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from butler.config import ModelConfig, get_butler_settings
from butler.transport.llm_client import LLMClient


@dataclass
class FallbackEntry:
    provider: str
    model: str
    api_key: str | None = None
    base_url: str | None = None

    @classmethod
    def from_model_config(cls, cfg: ModelConfig) -> FallbackEntry | None:
        if not cfg.provider and not cfg.model:
            return None
        settings = get_butler_settings()
        pc = settings.providers.get(cfg.provider) if cfg.provider else None
        return cls(
            provider=cfg.provider or (settings.default_provider or ""),
            model=cfg.model or (pc.model if pc else ""),
            api_key=pc.api_key if pc else None,
            base_url=pc.base_url if pc else None,
        )


def build_fallback_chain(
    primary: ModelConfig,
    extra: list[ModelConfig] | None = None,
) -> list[FallbackEntry]:
    """Build deduplicated fallback chain: primary first, then extras."""
    chain: list[FallbackEntry] = []
    seen: set[tuple[str, str]] = set()

    def _add(cfg: ModelConfig | None) -> None:
        if cfg is None:
            return
        entry = FallbackEntry.from_model_config(cfg)
        if entry is None:
            return
        key = (entry.provider, entry.model)
        if key in seen:
            return
        seen.add(key)
        chain.append(entry)

    _add(primary)
    for cfg in extra or []:
        _add(cfg)

    settings = get_butler_settings()
    if primary.provider == "minimax":
        for alt in ("deepseek", "qwen", "openai"):
            if alt in settings.providers:
                _add(ModelConfig(provider=alt, model=settings.providers[alt].model))

    return chain


def create_client_from_entry(entry: FallbackEntry, **kwargs: Any) -> LLMClient:
    return LLMClient(
        provider=entry.provider,
        model=entry.model,
        api_key=entry.api_key,
        base_url=entry.base_url,
        **kwargs,
    )

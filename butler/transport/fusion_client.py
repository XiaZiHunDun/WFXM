"""Trusted-model router for semantic fusion (skill/experience merge).

Distinct from ``auxiliary_client``: fusion tasks need a capable model
(``auxiliary.fusion`` or butler role stack), not the cheap compression path.
"""

from __future__ import annotations

import logging
from typing import Any

from butler.config import ModelConfig, get_butler_settings
from butler.transport.llm_client import LLMClient

logger = logging.getLogger(__name__)

_FUSION_SYSTEM = (
    "You merge overlapping knowledge records for a personal assistant. "
    "Preserve factual pointers (skill:, tool:, mcp:). Output only valid JSON when asked."
)


def resolve_fusion_config() -> ModelConfig:
    """``auxiliary.fusion`` → butler effective model → provider default."""
    settings = get_butler_settings()
    cfg = settings.get_auxiliary_task_config("fusion")
    if not cfg.is_empty():
        return cfg

    from butler.model_resolve import resolve_effective_model

    butler_cfg = resolve_effective_model("butler", settings=settings).config
    if not butler_cfg.is_empty():
        return butler_cfg

    preferred = (settings.default_provider or "minimax").strip()
    if preferred and (pc := settings.providers.get(preferred)):
        return ModelConfig(provider=preferred, model=pc.model or "")

    from butler.defaults.model_defaults import AUXILIARY_SCAN_PROVIDERS

    for name in AUXILIARY_SCAN_PROVIDERS:
        if pc := settings.providers.get(name):
            return ModelConfig(provider=name, model=pc.model or "")
    return ModelConfig(provider=preferred or "minimax", model="")


def create_fusion_client(**kwargs: Any) -> LLMClient:
    cfg = resolve_fusion_config()
    settings = get_butler_settings()
    pc = settings.providers.get(cfg.provider) if cfg.provider else None
    return LLMClient(
        provider=cfg.provider,
        model=cfg.model or (pc.model if pc else ""),
        api_key=pc.api_key if pc else None,
        base_url=pc.base_url if pc else None,
        max_tokens=cfg.max_tokens or 4096,
        temperature=cfg.temperature if cfg.temperature is not None else 0.2,
        **kwargs,
    )


def fusion_complete(
    prompt: str,
    *,
    system: str = _FUSION_SYSTEM,
    session_key: str = "",
) -> str:
    """Single-shot trusted-model completion for merge/fusion tasks."""
    client = create_fusion_client()
    resp = client.complete(
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
    )
    sk = session_key or _current_session_key()
    if sk and resp.usage:
        from butler.transport.fusion_client_ops import record_fusion_llm_cost_safe

        record_fusion_llm_cost_safe(sk, resp.usage)
    return resp.content or ""


def _current_session_key() -> str:
    from butler.transport.fusion_client_ops import current_fusion_session_key_safe

    return current_fusion_session_key_safe()


def make_fusion_llm_fn():
    """Sync callable for ``SkillConsolidator`` / experience merge."""
    from butler.transport.fusion_client_ops import fusion_complete_or_raise_unavailable

    def _call(prompt: str) -> str:
        return fusion_complete_or_raise_unavailable(fusion_complete, prompt)

    return _call


__all__ = [
    "create_fusion_client",
    "fusion_complete",
    "make_fusion_llm_fn",
    "resolve_fusion_config",
]

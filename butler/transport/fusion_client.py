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
        try:
            from butler.ops.cost_tracker import get_session_cost

            get_session_cost(sk).record_llm_call(
                input_tokens=getattr(resp.usage, "prompt_tokens", 0) or 0,
                output_tokens=getattr(resp.usage, "completion_tokens", 0) or 0,
            )
        except Exception:
            pass
    return resp.content or ""


def _current_session_key() -> str:
    try:
        from butler.core.session_key import get_current_session_key

        return str(get_current_session_key() or "")
    except Exception:
        return ""


def make_fusion_llm_fn():
    """Sync callable for ``SkillConsolidator`` / experience merge."""
    from butler.skills.consolidator import ConsolidatorLLMUnavailable

    def _call(prompt: str) -> str:
        try:
            return fusion_complete(prompt)
        except ConsolidatorLLMUnavailable:
            raise
        except Exception as exc:
            raise ConsolidatorLLMUnavailable(str(exc)) from exc

    return _call


__all__ = [
    "create_fusion_client",
    "fusion_complete",
    "make_fusion_llm_fn",
    "resolve_fusion_config",
]

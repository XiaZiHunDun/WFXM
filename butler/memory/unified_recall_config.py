"""Opt-in config for P3-H unified hybrid recall."""

from __future__ import annotations

from butler.env_parse import env_truthy, float_env
from butler.memory_settings import resolve_memory_config


def observation_recall_enabled() -> bool:
    cfg = resolve_memory_config()
    return env_truthy(
        "BUTLER_MEMORY_OBSERVATION_RECALL",
        default=cfg.observation_recall_enabled,
    )


def unified_recall_enabled() -> bool:
    cfg = resolve_memory_config()
    return env_truthy(
        "BUTLER_MEMORY_UNIFIED_RECALL",
        default=cfg.unified_recall_enabled,
    )


def unified_scope_weights() -> dict[str, float]:
    cfg = resolve_memory_config()
    return {
        "experience": cfg.unified_weight_experience,
        "project": cfg.unified_weight_project,
        "coding": cfg.unified_weight_coding,
    }


def observation_recall_boost() -> float:
    return resolve_memory_config().observation_recall_boost


__all__ = [
    "observation_recall_boost",
    "observation_recall_enabled",
    "unified_recall_enabled",
    "unified_scope_weights",
]

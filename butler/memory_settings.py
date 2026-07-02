"""Memory stack settings: ``config.yaml`` ``memory.*`` with env overrides."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import yaml

from butler.config import get_butler_settings
from butler.defaults.env_defaults import (
    MEMORY_ACCESS_BOOST,
    MEMORY_HALF_LIFE_DAYS,
    MEMORY_MAX_BYTES,
    MEMORY_MAX_LINES,
    MEMORY_SEMANTIC_SEARCH_LIMIT,
    MEMORY_VECTOR_HYBRID_WEIGHT,
    OBSERVATION_TTL_DAYS,
)
from butler.env_parse import env_truthy, float_env, int_env


@dataclass
class MemoryConfig:
    semantic_enabled: bool = False
    vector_hybrid_weight: float = MEMORY_VECTOR_HYBRID_WEIGHT
    fts_hybrid_weight: float = 1.0 - MEMORY_VECTOR_HYBRID_WEIGHT
    search_limit: int = MEMORY_SEMANTIC_SEARCH_LIMIT
    max_lines: int = MEMORY_MAX_LINES
    max_bytes: int = MEMORY_MAX_BYTES
    recall_layers_enabled: bool = True
    half_life_days: float = MEMORY_HALF_LIFE_DAYS
    access_boost: float = MEMORY_ACCESS_BOOST
    preread_enabled: bool = True
    observer_queue_enabled: bool = False
    observation_ttl_days: int = OBSERVATION_TTL_DAYS
    observation_max_rows: int = 0
    observation_recall_enabled: bool = False
    unified_recall_enabled: bool = False
    unified_weight_experience: float = 0.50
    unified_weight_project: float = 0.35
    unified_weight_coding: float = 0.15
    observation_recall_boost: float = 0.12
    metrics_persist: bool = True
    corrective_recall_enabled: bool = True
    private_tags_enabled: bool = True
    yaml_configured: bool = False


def _load_yaml_memory() -> dict[str, Any]:
    settings = get_butler_settings()
    path = settings.config_yaml_path
    if not path.is_file():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    mem = data.get("memory")
    return mem if isinstance(mem, dict) else {}


def _nested_dict(raw: dict[str, Any], key: str) -> dict[str, Any]:
    child = raw.get(key)
    return child if isinstance(child, dict) else {}


def _float_from_raw(raw: dict[str, Any], key: str, default: float) -> float:
    if key not in raw:
        return default
    try:
        return float(raw[key])
    except (TypeError, ValueError):
        return default


def _int_from_raw(raw: dict[str, Any], key: str, default: int) -> int:
    if key not in raw:
        return default
    try:
        return int(raw[key])
    except (TypeError, ValueError):
        return default


def _bool_from_raw(raw: dict[str, Any], key: str, default: bool) -> bool:
    if key not in raw:
        return default
    return bool(raw[key])


def resolve_memory_config() -> MemoryConfig:
    """Merge ``config.yaml`` ``memory.*`` with env (env wins)."""
    raw = _load_yaml_memory()
    yaml_configured = bool(raw)
    hybrid_raw = _nested_dict(raw, "hybrid")
    index_raw = _nested_dict(raw, "index")
    ranking_raw = _nested_dict(raw, "ranking")
    obs_raw = _nested_dict(raw, "observation")

    semantic_yaml_default = _bool_from_raw(raw, "semantic_enabled", False)
    semantic_enabled = env_truthy("BUTLER_SEMANTIC_MEMORY", default=semantic_yaml_default)

    vector_yaml = _float_from_raw(
        hybrid_raw,
        "vector_weight",
        _float_from_raw(raw, "vector_hybrid_weight", MEMORY_VECTOR_HYBRID_WEIGHT),
    )
    vector_weight = float_env(
        "BUTLER_VECTOR_HYBRID_WEIGHT",
        float(vector_yaml),
        min=0.0,
        max=1.0,
    )

    fts_yaml = hybrid_raw.get("fts_weight", raw.get("fts_hybrid_weight"))
    fts_override = os.getenv("BUTLER_FTS_HYBRID_WEIGHT", "").strip()
    if fts_override:
        try:
            fts_weight = max(0.0, min(1.0, float(fts_override)))
        except ValueError:
            fts_weight = 1.0 - vector_weight
    elif fts_yaml is not None and str(fts_yaml).strip() != "":
        try:
            fts_weight = max(0.0, min(1.0, float(fts_yaml)))
        except (TypeError, ValueError):
            fts_weight = 1.0 - vector_weight
    else:
        fts_weight = 1.0 - vector_weight

    search_yaml = _int_from_raw(raw, "search_limit", MEMORY_SEMANTIC_SEARCH_LIMIT)
    search_limit = int_env("BUTLER_SEMANTIC_SEARCH_LIMIT", search_yaml, min=1)

    max_lines_yaml = _int_from_raw(index_raw, "max_lines", _int_from_raw(raw, "max_lines", MEMORY_MAX_LINES))
    max_lines = int_env("BUTLER_MEMORY_MAX_LINES", max_lines_yaml, min=0)

    max_bytes_yaml = _int_from_raw(
        index_raw,
        "max_bytes",
        _int_from_raw(raw, "max_bytes", MEMORY_MAX_BYTES),
    )
    max_bytes = int_env("BUTLER_MEMORY_MAX_BYTES", max_bytes_yaml, min=0)

    recall_yaml = _bool_from_raw(raw, "recall_layers_enabled", True)
    recall_layers_enabled = env_truthy("BUTLER_MEMORY_RECALL_LAYERS", default=recall_yaml)

    half_life_yaml = _float_from_raw(
        ranking_raw,
        "half_life_days",
        _float_from_raw(raw, "half_life_days", MEMORY_HALF_LIFE_DAYS),
    )
    half_life_days = float_env(
        "BUTLER_MEMORY_HALF_LIFE_DAYS",
        float(half_life_yaml),
        min=1.0,
    )

    access_yaml = _float_from_raw(
        ranking_raw,
        "access_boost",
        _float_from_raw(raw, "access_boost", MEMORY_ACCESS_BOOST),
    )
    access_boost = float_env(
        "BUTLER_MEMORY_ACCESS_BOOST",
        float(access_yaml),
        min=0.0,
    )

    preread_yaml = _bool_from_raw(raw, "preread_enabled", True)
    preread_enabled = env_truthy("BUTLER_MEMORY_PREREAD", default=preread_yaml)

    observer_yaml = _bool_from_raw(raw, "observer_queue_enabled", False)
    observer_queue_enabled = env_truthy("BUTLER_MEMORY_OBSERVER_QUEUE", default=observer_yaml)

    ttl_yaml = _int_from_raw(obs_raw, "ttl_days", _int_from_raw(raw, "observation_ttl_days", OBSERVATION_TTL_DAYS))
    ttl_raw = os.getenv("BUTLER_OBSERVATION_TTL_DAYS", "").strip()
    if ttl_raw:
        try:
            observation_ttl_days = max(0, int(ttl_raw))
        except ValueError:
            observation_ttl_days = ttl_yaml
    else:
        observation_ttl_days = ttl_yaml

    max_rows_yaml = _int_from_raw(obs_raw, "max_rows", _int_from_raw(raw, "observation_max_rows", 0))
    max_rows_raw = os.getenv("BUTLER_MEMORY_OBSERVATION_MAX_ROWS", "").strip()
    if max_rows_raw:
        try:
            observation_max_rows = max(0, int(max_rows_raw))
        except ValueError:
            observation_max_rows = max_rows_yaml
    else:
        observation_max_rows = max_rows_yaml

    unified_raw = _nested_dict(raw, "unified_recall")
    observation_recall_yaml = _bool_from_raw(
        obs_raw,
        "recall_enabled",
        _bool_from_raw(unified_raw, "observation_recall_enabled", False),
    )
    observation_recall_enabled = env_truthy(
        "BUTLER_MEMORY_OBSERVATION_RECALL",
        default=observation_recall_yaml,
    )
    unified_recall_yaml = _bool_from_raw(unified_raw, "enabled", False)
    unified_recall_enabled = env_truthy(
        "BUTLER_MEMORY_UNIFIED_RECALL",
        default=unified_recall_yaml,
    )
    unified_weight_experience = float_env(
        "BUTLER_MEMORY_UNIFIED_WEIGHT_EXPERIENCE",
        _float_from_raw(unified_raw, "weight_experience", 0.50),
        min=0.0,
        max=1.0,
    )
    unified_weight_project = float_env(
        "BUTLER_MEMORY_UNIFIED_WEIGHT_PROJECT",
        _float_from_raw(unified_raw, "weight_project", 0.35),
        min=0.0,
        max=1.0,
    )
    unified_weight_coding = float_env(
        "BUTLER_MEMORY_UNIFIED_WEIGHT_CODING",
        _float_from_raw(unified_raw, "weight_coding", 0.15),
        min=0.0,
        max=1.0,
    )
    observation_recall_boost = float_env(
        "BUTLER_MEMORY_OBSERVATION_RECALL_BOOST",
        _float_from_raw(obs_raw, "recall_boost", _float_from_raw(unified_raw, "observation_boost", 0.12)),
        min=0.0,
        max=1.0,
    )

    metrics_yaml = _bool_from_raw(raw, "metrics_persist", True)
    metrics_persist = env_truthy("BUTLER_MEMORY_METRICS_PERSIST", default=metrics_yaml)

    corrective_yaml = _bool_from_raw(raw, "corrective_recall_enabled", True)
    corrective_recall_enabled = env_truthy("BUTLER_CORRECTIVE_RECALL", default=corrective_yaml)

    private_yaml = _bool_from_raw(raw, "private_tags_enabled", True)
    private_tags_enabled = env_truthy("BUTLER_MEMORY_PRIVATE_TAGS", default=private_yaml)

    return MemoryConfig(
        semantic_enabled=semantic_enabled,
        vector_hybrid_weight=vector_weight,
        fts_hybrid_weight=fts_weight,
        search_limit=search_limit,
        max_lines=max_lines,
        max_bytes=max_bytes,
        recall_layers_enabled=recall_layers_enabled,
        half_life_days=half_life_days,
        access_boost=access_boost,
        preread_enabled=preread_enabled,
        observer_queue_enabled=observer_queue_enabled,
        observation_ttl_days=observation_ttl_days,
        observation_max_rows=observation_max_rows,
        observation_recall_enabled=observation_recall_enabled,
        unified_recall_enabled=unified_recall_enabled,
        unified_weight_experience=unified_weight_experience,
        unified_weight_project=unified_weight_project,
        unified_weight_coding=unified_weight_coding,
        observation_recall_boost=observation_recall_boost,
        metrics_persist=metrics_persist,
        corrective_recall_enabled=corrective_recall_enabled,
        private_tags_enabled=private_tags_enabled,
        yaml_configured=yaml_configured,
    )


def format_memory_config_source_line() -> str:
    """One-line effective config summary for ``/诊断``."""
    cfg = resolve_memory_config()
    source = "yaml+env" if cfg.yaml_configured else "env/默认"
    return (
        f"  记忆配置: 向量={'开' if cfg.semantic_enabled else '关'}, "
        f"分层召回={'开' if cfg.recall_layers_enabled else '关'}, "
        f"混合 {cfg.vector_hybrid_weight:.2f}/{cfg.fts_hybrid_weight:.2f}, "
        f"来源={source}"
    )


__all__ = [
    "MemoryConfig",
    "format_memory_config_source_line",
    "resolve_memory_config",
]

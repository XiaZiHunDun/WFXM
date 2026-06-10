"""Environment flags for optional vector semantic memory (Butler-local)."""

from __future__ import annotations

import os

from butler.memory_settings import resolve_memory_config


def semantic_memory_enabled() -> bool:
    """When true, maintain memory_vectors.db and use hybrid recall."""
    return resolve_memory_config().semantic_enabled


def resolve_embedding_config() -> tuple[str, str]:
    """``config.yaml`` embedding.* → env ``BUTLER_EMBEDDING_*`` (env wins)."""
    from butler.config import get_butler_settings
    from butler.defaults.model_defaults import (
        DEFAULT_EMBEDDING_MODEL,
        DEFAULT_EMBEDDING_PROVIDER,
    )

    settings = get_butler_settings()
    yaml_emb = settings.embedding if isinstance(settings.embedding, dict) else {}

    provider = (os.getenv("BUTLER_EMBEDDING_PROVIDER", "") or "").strip()
    if not provider:
        provider = str(yaml_emb.get("provider") or DEFAULT_EMBEDDING_PROVIDER).strip()

    model = (os.getenv("BUTLER_EMBEDDING_MODEL", "") or "").strip()
    if not model:
        model = str(yaml_emb.get("model") or DEFAULT_EMBEDDING_MODEL).strip()

    return provider.lower(), model


def embedding_provider_name() -> str:
    """local | openai | minimax | fastembed."""
    return resolve_embedding_config()[0]


def embedding_model_name() -> str:
    return resolve_embedding_config()[1]


def hybrid_vector_weight() -> float:
    """Blend weight for vector rank vs FTS in hybrid (0–1, vector share)."""
    return resolve_memory_config().vector_hybrid_weight


def hybrid_fts_weight() -> float:
    """FTS share in hybrid merge (default 1 - vector weight)."""
    return resolve_memory_config().fts_hybrid_weight


def semantic_search_limit(default: int = 8) -> int:
    cfg = resolve_memory_config()
    if default != 8:
        from butler.env_parse import int_env

        return int_env("BUTLER_SEMANTIC_SEARCH_LIMIT", default, min=1)
    return cfg.search_limit

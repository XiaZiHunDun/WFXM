"""Environment flags for optional vector semantic memory (Butler-local)."""

from __future__ import annotations

import os


def _truthy(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def semantic_memory_enabled() -> bool:
    """When true, maintain memory_vectors.db and use hybrid recall."""
    return _truthy("BUTLER_SEMANTIC_MEMORY", "0")


def embedding_provider_name() -> str:
    """local | openai | minimax (openai/minimax reserved for P1)."""
    return (os.getenv("BUTLER_EMBEDDING_PROVIDER", "local") or "local").strip().lower()


def embedding_model_name() -> str:
    return (os.getenv("BUTLER_EMBEDDING_MODEL", "hashing-v1") or "hashing-v1").strip()


def hybrid_vector_weight() -> float:
    """Blend weight for vector rank vs FTS in hybrid (0–1, vector share)."""
    try:
        return max(0.0, min(1.0, float(os.getenv("BUTLER_VECTOR_HYBRID_WEIGHT", "0.5"))))
    except ValueError:
        return 0.5


def hybrid_fts_weight() -> float:
    """FTS share in hybrid merge (default 1 - vector weight)."""
    override = os.getenv("BUTLER_FTS_HYBRID_WEIGHT", "").strip()
    if override:
        try:
            return max(0.0, min(1.0, float(override)))
        except ValueError:
            pass
    return 1.0 - hybrid_vector_weight()


def semantic_search_limit(default: int = 8) -> int:
    try:
        return max(1, int(os.getenv("BUTLER_SEMANTIC_SEARCH_LIMIT", str(default))))
    except ValueError:
        return default

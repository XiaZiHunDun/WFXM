"""Best-effort / fail-loud helpers for embedding resolution (P0-A)."""

from __future__ import annotations

import logging
from typing import Any

from butler.core.best_effort import safe_best_effort

_fail_loud_logger = logging.getLogger("butler.memory.embedding")


def clear_embedding_degradation_safe() -> None:
    def _run() -> None:
        from butler.ops.degradation_registry import clear_degradation

        clear_degradation("embedding")

    safe_best_effort(_run, label="embedding.degradation_clear", default=None)


def register_embedding_degradation_safe(*, provider: str, model: str) -> None:
    def _run() -> None:
        from butler.defaults.model_defaults import DEFAULT_EMBEDDING_MODEL
        from butler.ops.degradation_registry import register_degradation

        register_degradation(
            "embedding",
            f"请求 {provider or '?'}/{model or '?'} → {DEFAULT_EMBEDDING_MODEL}",
        )

    safe_best_effort(_run, label="embedding.degradation_register", default=None)


def resolve_fastembed_loud(model: str) -> Any | None:
    """Try to instantiate a fastembed embedder; return None if unavailable."""
    from butler.defaults.model_defaults import DEFAULT_EMBEDDING_MODEL
    from butler.memory.embedding import FastEmbedEmbedder

    try:
        m = (
            model
            if model and model != DEFAULT_EMBEDDING_MODEL
            else FastEmbedEmbedder._DEFAULT_MODEL
        )
        embedder = FastEmbedEmbedder(model_name=m)
        probe = embedder.embed("ping")
        if probe:
            return embedder
    except ImportError:
        _fail_loud_logger.error(
            "BUTLER_EMBEDDING_PROVIDER=fastembed but fastembed not installed; "
            "pip install 'butler-system[embeddings]'"
        )
    except Exception as exc:
        _fail_loud_logger.error(
            "fastembed init failed (%s); falling back to local hashing",
            exc,
            exc_info=exc,
        )
    return None


def probe_api_embedder_loud(api: Any, *, provider: str) -> Any | None:
    try:
        probe = api.embed("ping")
        if probe:
            return api
    except Exception as exc:
        _fail_loud_logger.error(
            "Embedding provider %r probe failed (%s) → fallback to HashingEmbedder",
            provider,
            exc,
            exc_info=exc,
        )
    return None

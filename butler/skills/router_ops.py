"""Best-effort helpers for skill routing (P0-A)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from butler.core.best_effort import safe_best_effort


def get_skill_embedder_safe() -> Any | None:
    import os

    if os.getenv("BUTLER_SKILL_SEMANTIC_ROUTING", "1").strip() != "1":
        return None

    def _run() -> Any | None:
        from butler.memory.embedding import get_embedder

        embedder = get_embedder()
        if embedder.model_id.startswith("hashing"):
            return None
        return embedder

    return safe_best_effort(_run, label="skills.router.embedder", default=None)


def embed_text_safe(embedder: Any, text: str) -> list[float]:
    def _run() -> list[float]:
        return list(embedder.embed(text))

    result = safe_best_effort(_run, label="skills.router.embed_text", default=[])
    return result if isinstance(result, list) else []


def load_skill_content_safe(loader: Callable[[str], dict[str, Any] | None], name: str) -> dict[str, Any] | None:
    return safe_best_effort(
        lambda: loader(name),
        label="skills.router.content_load",
        default=None,
    )


def batch_load_skill_content_safe(
    loader: Callable[[list[str]], dict[str, dict[str, Any]]],
    names: list[str],
) -> dict[str, dict[str, Any]]:
    def _run() -> dict[str, dict[str, Any]]:
        loaded = loader(names)
        return loaded if isinstance(loaded, dict) else {}

    result = safe_best_effort(_run, label="skills.router.batch_content_load", default={})
    return result if isinstance(result, dict) else {}

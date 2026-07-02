"""Model context binding helpers (P0-A)."""

from __future__ import annotations

from typing import Any

from butler.core.best_effort import safe_best_effort


def infer_context_length_safe(loop: Any, *, provider: str, model: str) -> None:
    def _run() -> None:
        from butler.transport.model_context import infer_context_length

        loop.config.max_context_tokens = infer_context_length(provider, model)

    safe_best_effort(_run, label="context_transform_registry.context_length", default=None)

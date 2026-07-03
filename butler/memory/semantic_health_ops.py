"""Semantic index health best-effort helpers (P0-A)."""

from __future__ import annotations

from typing import Any

from butler.core.best_effort import safe_best_effort


def count_experience_vectors_safe(semantic_index: Any, source: str) -> int:
    def _run() -> int:
        return int(semantic_index.count_by_source(source))

    result = safe_best_effort(
        _run,
        label="semantic_health.count_experience_vectors",
        default=0,
    )
    return int(result) if isinstance(result, int) else 0

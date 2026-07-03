"""Output grounding best-effort helpers (P0-A)."""

from __future__ import annotations

from butler.core.best_effort import safe_best_effort


def estimate_prefetch_used_count_safe(reply: str, snippets: list[str]) -> int | None:
    def _run() -> int:
        from butler.memory.prefetch_retrieval_metrics import estimate_prefetch_used_count

        return int(estimate_prefetch_used_count(reply, snippets))

    result = safe_best_effort(
        _run,
        label="output_grounding.prefetch_used",
        default=None,
    )
    return int(result) if isinstance(result, int) else None

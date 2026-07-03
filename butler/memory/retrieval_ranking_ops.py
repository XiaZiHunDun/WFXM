"""Retrieval ranking eval/metrics best-effort helpers (P0-A)."""

from __future__ import annotations

from butler.core.best_effort import safe_best_effort


def effective_memory_half_life_days_safe(base: float) -> float | None:
    def _run() -> float:
        from butler.ops.eval_config_overrides import effective_memory_half_life_days

        return float(effective_memory_half_life_days(base))

    result = safe_best_effort(
        _run,
        label="retrieval_ranking.eval_half_life",
        default=None,
    )
    return float(result) if isinstance(result, (int, float)) else None


def record_decay_evaluation_safe(*, total_important: int, killed: int) -> None:
    def _run() -> None:
        from butler.memory.memory_metrics import get_collector

        get_collector().on_decay_evaluation(
            total_important=total_important,
            killed=killed,
        )

    safe_best_effort(_run, label="retrieval_ranking.decay_metrics", default=None)

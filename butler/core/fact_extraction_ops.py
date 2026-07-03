"""Fact extraction metrics best-effort helpers (P0-A)."""

from __future__ import annotations

from butler.core.best_effort import safe_best_effort


def record_fact_extraction_metrics_safe(*, pre_count: int, post_count: int) -> None:
    def _run() -> None:
        from butler.memory.memory_metrics import get_collector

        get_collector().on_fact_extraction(pre_count=pre_count, post_count=post_count)

    safe_best_effort(_run, label="fact_extraction.metrics", default=None)


def record_fact_anchor_survival_safe(*, store_count: int, anchor_count: int) -> None:
    def _run() -> None:
        from butler.memory.memory_metrics import get_collector

        get_collector().on_fact_anchor_survival(
            store_count=store_count,
            anchor_count=anchor_count,
        )

    safe_best_effort(_run, label="fact_extraction.anchor_survival", default=None)

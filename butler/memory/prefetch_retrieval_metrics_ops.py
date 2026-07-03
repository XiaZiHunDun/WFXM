"""Prefetch retrieval metrics best-effort helpers (P0-A)."""

from __future__ import annotations

from typing import Any

from butler.core.best_effort import safe_best_effort


def persist_prefetch_retrieval_used_safe(used: int, health: dict[str, Any]) -> None:
    def _run() -> None:
        from butler.memory.memory_metrics import get_collector
        from butler.memory.metrics_persist import flush_memory_metrics

        get_collector().add_retrieval_used(used)
        health["memory_prefetch_retrieval_used"] = used
        flush_memory_metrics()

    safe_best_effort(_run, label="prefetch_retrieval_metrics.persist", default=None)

"""Memory eval LangFuse bridge best-effort helpers (P0-A)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from butler.core.best_effort import safe_best_effort

logger = logging.getLogger(__name__)


def run_memory_benchmarks_safe(butler_home: Path) -> tuple[Any | None, str | None]:
    try:
        from butler.memory.memory_benchmark import run_all_benchmarks

        return run_all_benchmarks(butler_home), None
    except Exception as exc:
        logger.warning("Memory benchmark failed: %s", exc)
        return None, str(exc)


def push_memory_benchmark_dataset_safe(report: Any) -> dict[str, Any]:
    def _run() -> dict[str, Any]:
        from butler.ops.memory_eval import push_memory_benchmark_dataset

        return push_memory_benchmark_dataset(report)

    result = safe_best_effort(
        _run,
        label="memory_eval.dataset_push",
        default={},
    )
    return result if isinstance(result, dict) else {}


def push_memory_benchmark_scores_safe(report: Any) -> dict[str, Any]:
    def _run() -> dict[str, Any]:
        from butler.ops.memory_eval import push_memory_scores

        return push_memory_scores(report)

    result = safe_best_effort(
        _run,
        label="memory_eval.score_push",
        default={},
    )
    return result if isinstance(result, dict) else {}

"""Memory benchmark fail-loud helpers (P0-A)."""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from butler.memory.memory_benchmark import BenchmarkCategory, BenchmarkExpected, BenchmarkResult


def run_mb_loud(
    run: Callable[[], BenchmarkResult],
    *,
    benchmark_id: str,
    category: BenchmarkCategory,
    expected: BenchmarkExpected,
    t0: float,
) -> BenchmarkResult:
    from butler.memory.memory_benchmark import BenchmarkResult

    try:
        return run()
    except Exception as exc:
        return BenchmarkResult(
            benchmark_id=benchmark_id,
            category=category,
            expected=expected,
            error=str(exc),
            elapsed_ms=(time.time() - t0) * 1000,
        )


def run_benchmark_task_loud(
    bench_fn: Callable[[Path], BenchmarkResult],
    home: Path,
    *,
    fallback_id: str,
    fallback_category: BenchmarkCategory | None = None,
) -> BenchmarkResult:
    from butler.memory.memory_benchmark import (
        BenchmarkCategory,
        BenchmarkExpected,
        BenchmarkResult,
    )

    category = fallback_category or BenchmarkCategory.EXACT_RECALL
    t0 = time.time()
    try:
        return bench_fn(home)
    except Exception as exc:
        return BenchmarkResult(
            benchmark_id=fallback_id,
            category=category,
            expected=BenchmarkExpected(),
            error=str(exc),
            elapsed_ms=(time.time() - t0) * 1000,
        )


__all__ = ["run_benchmark_task_loud", "run_mb_loud"]

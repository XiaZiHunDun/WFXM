"""Memory benchmark → LangFuse evaluation bridge.

Converts MB1-MB7 memory benchmark results and runtime metrics
to LangFuse evaluation datasets and scores.

Usage::

    from butler.ops.memory_eval import run_and_push_memory_eval
    summary = run_and_push_memory_eval(butler_home)
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DATASET_NAME = "butler-memory-benchmark"

MB_DESCRIPTIONS: dict[str, str] = {
    "MB1": "Exact recall — write profile, query with original text",
    "MB2": "Semantic recall — write experience, query with rewrite",
    "MB3": "Cross-session persistence — write, restart, query",
    "MB4": "Decay behavior — write, simulate 60 days, check ranking",
    "MB5": "Capacity pressure — write many, query earliest",
    "MB6": "Fact compaction — extract facts, compress, check anchors",
    "MB7": "Injection safety — memory with injection pattern, filter",
}


def benchmark_report_to_dataset_items(report: Any) -> list[Any]:
    """Convert a BenchmarkReport into LangFuse DatasetItems.

    Each MB task becomes a dataset item with:
      - input: the task definition
      - expected_output: thresholds and expected behavior
    """
    from butler.ops.eval_bridge import DatasetItem

    items = []
    for r in getattr(report, "results", []):
        bid = r.benchmark_id
        items.append(DatasetItem(
            input={
                "benchmark_id": bid,
                "category": r.category.value if hasattr(r.category, "value") else str(r.category),
                "description": MB_DESCRIPTIONS.get(bid, ""),
            },
            expected_output={
                "min_recall": getattr(r.expected, "min_recall", 0.0),
                "min_precision": getattr(r.expected, "min_precision", 0.0),
                "min_survival_rate": getattr(r.expected, "min_survival_rate", 0.0),
                "max_decay_error": getattr(r.expected, "max_decay_error", 1.0),
                "must_filter": getattr(r.expected, "must_filter", False),
            },
            metadata={
                "score": r.score,
                "passed": r.passed,
                "elapsed_ms": getattr(r, "elapsed_ms", 0.0),
                "details": getattr(r, "details", {}),
                "error": getattr(r, "error", ""),
            },
            source_id=bid,
        ))

    return items


def benchmark_report_to_scores(report: Any, trace_id: str = "") -> list[Any]:
    """Convert a BenchmarkReport to LangFuse EvalScores."""
    from butler.ops.eval_bridge import EvalScore, memory_benchmark_to_scores

    scores = memory_benchmark_to_scores(report)
    if trace_id:
        for s in scores:
            s.trace_id = trace_id

    return scores


def memory_session_to_scores(metrics: Any, trace_id: str = "") -> list[Any]:
    """Convert SessionMemoryMetrics to LangFuse EvalScores."""
    from butler.ops.eval_bridge import memory_metrics_to_scores

    scores = memory_metrics_to_scores(metrics)
    if trace_id:
        for s in scores:
            s.trace_id = trace_id

    return scores


def push_memory_benchmark_dataset(report: Any) -> dict[str, Any]:
    """Push memory benchmark results as a LangFuse dataset.

    Returns summary dict.
    """
    from butler.ops.eval_bridge import create_dataset, push_dataset_items

    summary: dict[str, Any] = {
        "dataset_items": 0,
        "dataset_created": False,
        "errors": [],
    }

    ds_id = create_dataset(DATASET_NAME, "Butler memory benchmark MB1-MB7")
    if ds_id:
        summary["dataset_created"] = True

    items = benchmark_report_to_dataset_items(report)
    ds_report = push_dataset_items(DATASET_NAME, items)
    summary["dataset_items"] = ds_report.dataset_items_pushed
    summary["errors"] = ds_report.errors

    return summary


def push_memory_scores(report: Any, metrics: Any = None, trace_id: str = "") -> dict[str, Any]:
    """Push both benchmark scores and runtime metrics to LangFuse.

    Returns summary dict.
    """
    from butler.ops.eval_bridge import push_scores

    all_scores = benchmark_report_to_scores(report, trace_id=trace_id)
    if metrics is not None:
        all_scores.extend(memory_session_to_scores(metrics, trace_id=trace_id))

    push_report = push_scores(all_scores)
    return {
        "scores_pushed": push_report.scores_pushed,
        "scores_failed": push_report.scores_failed,
        "total_scores": len(all_scores),
        "errors": push_report.errors,
    }


def run_and_push_memory_eval(butler_home: Path | None = None) -> dict[str, Any]:
    """Run memory benchmarks and push results to LangFuse.

    Combines:
      1. Run MB1-MB7 benchmarks
      2. Push as dataset items
      3. Push as evaluation scores

    Returns combined summary.
    """
    import tempfile

    butler_home = butler_home or Path(tempfile.mkdtemp(prefix="butler_bench_"))

    summary: dict[str, Any] = {
        "benchmark_run": {},
        "dataset_push": {},
        "score_push": {},
    }

    from butler.ops.memory_eval_ops import (
        push_memory_benchmark_dataset_safe,
        push_memory_benchmark_scores_safe,
        run_memory_benchmarks_safe,
    )

    report, bench_err = run_memory_benchmarks_safe(butler_home)
    if report is None:
        summary["benchmark_run"] = {"error": bench_err or "benchmark failed"}
        return summary
    summary["benchmark_run"] = report.summary()

    ds_push = push_memory_benchmark_dataset_safe(report)
    summary["dataset_push"] = ds_push if ds_push else {"error": "dataset push failed"}

    score_push = push_memory_benchmark_scores_safe(report)
    summary["score_push"] = score_push if score_push else {"error": "score push failed"}

    return summary

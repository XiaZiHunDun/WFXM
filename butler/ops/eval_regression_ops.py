"""Eval regression gate best-effort helpers (P0-A)."""

from __future__ import annotations

import logging
from typing import Any

from butler.core.best_effort import safe_best_effort

logger = logging.getLogger(__name__)


def run_b9_regression_benchmark_safe() -> tuple[Any | None, str | None]:
    try:
        from butler.dev_engine.llm_delegate_benchmark import B9Mode, run_llm_delegate_benchmarks

        return run_llm_delegate_benchmarks(mode=B9Mode.ORACLE), None
    except Exception as exc:
        logger.warning("B9 benchmark in regression gate failed: %s", exc)
        return None, str(exc)


def push_regression_scores_safe(
    *,
    dev: Any,
    mem: Any,
    b9: Any | None,
) -> tuple[int, str | None]:
    def _run() -> int:
        from butler.ops.eval_bridge import (
            dev_benchmark_to_scores,
            llm_benchmark_to_scores,
            memory_benchmark_to_scores,
            push_scores,
        )

        scores = dev_benchmark_to_scores(dev) + memory_benchmark_to_scores(mem)
        if b9 is not None:
            scores.extend(llm_benchmark_to_scores(b9))
        push_report = push_scores(scores)
        return int(push_report.scores_pushed)

    result = safe_best_effort(
        _run,
        label="eval_regression.push_scores",
        default=None,
    )
    if result is None:
        return 0, "langfuse_push failed"
    return int(result), None


def sync_eval_datasets_safe(*, dev: Any, mem: Any) -> tuple[bool, list[str]]:
    def _run() -> tuple[bool, list[str]]:
        from butler.ops.dev_eval import sync_all_eval_datasets

        ds_summary = sync_all_eval_datasets(dev_report=dev, mem_report=mem)
        synced = bool(ds_summary.get("any_pushed"))
        errors = [str(err) for err in (ds_summary.get("errors") or [])]
        return synced, errors

    result = safe_best_effort(
        _run,
        label="eval_regression.dataset_sync",
        default=None,
    )
    if result is None:
        return False, ["dataset_sync failed"]
    synced, errors = result
    return bool(synced), list(errors)

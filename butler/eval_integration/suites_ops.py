"""Eval suite LangFuse push best-effort helpers (P0-A)."""

from __future__ import annotations

from typing import Any


def push_b9_oracle_scores_safe(report: Any) -> None:
    try:
        from butler.ops.eval_bridge import llm_benchmark_to_scores, push_scores

        push_scores(llm_benchmark_to_scores(report))
    except Exception:
        pass


def push_memory_mb_scores_safe(report: Any) -> None:
    try:
        from butler.ops.memory_eval import push_memory_scores

        push_memory_scores(report)
    except Exception:
        pass

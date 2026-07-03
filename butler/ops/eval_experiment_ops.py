"""Eval experiment best-effort helpers (P0-A)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from butler.core.best_effort import safe_best_effort

logger = logging.getLogger(__name__)


def run_variant_benchmark_safe(
    variant: str,
    patch: dict[str, Any],
    *,
    workspace: Path | None,
    include_swe: bool,
    result_factory: Any,
) -> Any:
    from butler.dev_engine.llm_delegate_benchmark import resolve_b9_mode, run_llm_delegate_benchmarks
    from butler.ops.eval_config_overrides import temporary_overrides

    result = result_factory(variant=variant)
    try:
        with temporary_overrides(patch):
            mode = resolve_b9_mode()
            result.mode = mode.value
            b9 = run_llm_delegate_benchmarks(workspace=workspace, mode=mode)
            result.b9_passed = b9.passed
            result.b9_total = b9.total
            result.b9_pass_rate = b9.pass_rate

            if include_swe:
                from butler.ops.swebench_live_eval import run_swebench_live_benchmark

                swe = run_swebench_live_benchmark(workspace=workspace, mode=mode.value)
                result.swe_passed = swe.passed
                result.swe_total = swe.total
                result.swe_pass_rate = swe.pass_rate
    except Exception as exc:
        logger.warning("experiment variant %s failed: %s", variant, exc)
        result.errors.append(str(exc))
    return result


def push_experiment_scores_safe(scores: list[Any]) -> None:
    def _run() -> None:
        from butler.ops.eval_bridge import push_scores

        push_scores(scores)

    safe_best_effort(_run, label="eval_experiment.push_scores", default=None)


def promote_experiment_winner_safe(variants: list[Any]) -> dict[str, Any] | None:
    def _run() -> dict[str, Any]:
        from butler.ops.eval_config_overrides import promote_b9_experiment_winner

        promoted = promote_b9_experiment_winner(variants)
        return promoted if isinstance(promoted, dict) else {}

    result = safe_best_effort(
        _run,
        label="eval_experiment.promote_winner",
        default=None,
    )
    return result if isinstance(result, dict) and result else None

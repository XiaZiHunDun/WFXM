"""LangFuse-oriented eval experiments — compare dev delegate variants (phase 3).

Runs B9 (+ optional SWE live subset) under temporary ``eval_overrides`` patches
and pushes scores named ``eval_experiment.{variant}.*`` for UI comparison.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_STRICT_CK_PATCH: dict[str, Any] = {
    "coding_knowledge_strict_experience": True,
    "coding_guidance_max_cases": 8,
}
_DELEGATE_RESCUE_PATCH: dict[str, Any] = {
    "dev_max_fix_rounds": 4,
    "delegate_max_iterations": 32,
    "dev_auto_verify_levels": "lint,typecheck,test",
}
_FAILURE_CLASS_PATCH: dict[str, Any] = {
    **_DELEGATE_RESCUE_PATCH,
    **_STRICT_CK_PATCH,
    "b9_enhanced_delegate_context": True,
}

EXPERIMENT_VARIANTS: dict[str, dict[str, Any]] = {
    "baseline": {},
    "strict_ck": dict(_STRICT_CK_PATCH),
    "delegate_rescue": dict(_DELEGATE_RESCUE_PATCH),
    "full_verify": {
        "dev_auto_verify_levels": "lint,typecheck,test,build",
        "coding_guidance_max_cases": 8,
    },
    "strict_ck_rescue": {**_STRICT_CK_PATCH, **_DELEGATE_RESCUE_PATCH},
    "failure_class": dict(_FAILURE_CLASS_PATCH),
}


@dataclass
class VariantResult:
    variant: str
    b9_passed: int = 0
    b9_total: int = 0
    b9_pass_rate: float = 0.0
    swe_passed: int = 0
    swe_total: int = 0
    swe_pass_rate: float = 0.0
    mode: str = "oracle"
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "variant": self.variant,
            "b9": f"{self.b9_passed}/{self.b9_total}",
            "b9_pass_rate": round(self.b9_pass_rate, 4),
            "swe": f"{self.swe_passed}/{self.swe_total}",
            "swe_pass_rate": round(self.swe_pass_rate, 4),
            "mode": self.mode,
            "errors": self.errors,
        }


@dataclass
class ExperimentReport:
    experiment_id: str
    variants: list[VariantResult] = field(default_factory=list)
    include_swe: bool = False
    timestamp: float = field(default_factory=time.time)

    def summary(self) -> dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "include_swe": self.include_swe,
            "variants": [v.to_dict() for v in self.variants],
            "timestamp": self.timestamp,
        }


def _audit_path() -> Path:
    from butler.config import get_butler_home

    return get_butler_home() / "audit" / "eval_experiments.jsonl"


def _append_audit(record: dict[str, Any]) -> None:
    path = _audit_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    record.setdefault("ts", time.time())
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def variant_to_scores(
    experiment_id: str,
    result: VariantResult,
) -> list[Any]:
    from butler.ops.eval_bridge import EvalScore

    scores = [
        EvalScore(
            name=f"eval_experiment.{experiment_id}.{result.variant}.b9_pass_rate",
            value=result.b9_pass_rate,
            comment=f"{result.b9_passed}/{result.b9_total} mode={result.mode}",
            category="eval_experiment",
            metadata={"variant": result.variant, "experiment_id": experiment_id},
        ),
    ]
    if result.swe_total:
        scores.append(
            EvalScore(
                name=f"eval_experiment.{experiment_id}.{result.variant}.swe_live_pass_rate",
                value=result.swe_pass_rate,
                comment=f"{result.swe_passed}/{result.swe_total} mode={result.mode}",
                category="eval_experiment",
                metadata={"variant": result.variant, "experiment_id": experiment_id},
            )
        )
    return scores


def run_variant_benchmark(
    variant: str,
    patch: dict[str, Any],
    *,
    workspace: Path | None = None,
    include_swe: bool = False,
) -> VariantResult:
    from butler.dev_engine.llm_delegate_benchmark import resolve_b9_mode, run_llm_delegate_benchmarks
    from butler.ops.eval_config_overrides import temporary_overrides

    result = VariantResult(variant=variant)
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


def run_eval_experiment(
    *,
    experiment_id: str = "dev-delegate",
    variants: dict[str, dict[str, Any]] | None = None,
    workspace: Path | None = None,
    include_swe: bool = False,
    push_langfuse: bool = True,
) -> ExperimentReport:
    variant_map = variants or EXPERIMENT_VARIANTS
    report = ExperimentReport(experiment_id=experiment_id, include_swe=include_swe)

    all_scores: list[Any] = []
    for name, patch in variant_map.items():
        vr = run_variant_benchmark(
            name, patch, workspace=workspace, include_swe=include_swe,
        )
        report.variants.append(vr)
        all_scores.extend(variant_to_scores(experiment_id, vr))

    summary = report.summary()
    _append_audit(summary)

    if push_langfuse:
        try:
            from butler.ops.eval_bridge import push_scores

            push_scores(all_scores)
        except Exception as exc:
            logger.warning("experiment LangFuse push failed: %s", exc)

    try:
        from butler.ops.eval_config_overrides import promote_b9_experiment_winner

        promoted = promote_b9_experiment_winner(report.variants)
        if promoted:
            _append_audit({"type": "experiment_winner_promoted", **promoted})
    except Exception as exc:
        logger.warning("experiment winner promote failed: %s", exc)

    return report


__all__ = [
    "EXPERIMENT_VARIANTS",
    "ExperimentReport",
    "VariantResult",
    "run_eval_experiment",
    "variant_to_scores",
]

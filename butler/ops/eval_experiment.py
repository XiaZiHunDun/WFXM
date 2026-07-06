"""LangFuse-oriented eval experiments — compare dev delegate variants (phase 3).

Runs B9 (+ optional SWE live subset) under temporary ``eval_overrides`` patches
and pushes scores named ``eval_experiment.{variant}.*`` for UI comparison.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

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

    return cast(Path, get_butler_home()) / "audit" / "eval_experiments.jsonl"


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
    from butler.ops.eval_experiment_ops import run_variant_benchmark_safe

    return cast(
        VariantResult,
        run_variant_benchmark_safe(
        variant,
        patch,
        workspace=workspace,
        include_swe=include_swe,
        result_factory=VariantResult,
        ),
    )


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
        from butler.ops.eval_experiment_ops import push_experiment_scores_safe

        push_experiment_scores_safe(all_scores)

    from butler.ops.eval_experiment_ops import promote_experiment_winner_safe

    promoted = promote_experiment_winner_safe(report.variants)
    if promoted:
        _append_audit({"type": "experiment_winner_promoted", **promoted})

    return report


__all__ = [
    "EXPERIMENT_VARIANTS",
    "ExperimentReport",
    "VariantResult",
    "run_eval_experiment",
    "variant_to_scores",
]

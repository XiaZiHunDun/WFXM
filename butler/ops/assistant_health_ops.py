"""Assistant health metric load best-effort helpers (P0-A)."""

from __future__ import annotations

from typing import Any

from butler.core.best_effort import safe_best_effort


def read_langfuse_averages_safe(lookback_hours: float) -> dict[str, float]:
    def _run() -> dict[str, float]:
        from butler.ops.assistant_health import _avg_scores_by_name
        from butler.ops.eval_feedback import read_recent_scores

        return dict(_avg_scores_by_name(read_recent_scores(lookback_hours=lookback_hours)))

    result = safe_best_effort(
        _run,
        label="assistant_health.langfuse_scores",
        default={},
    )
    return dict(result) if isinstance(result, dict) else {}


def load_audit_health_metrics_safe() -> tuple[dict[str, float], dict[str, str]]:
    def _run() -> tuple[dict[str, float], dict[str, str]]:
        from butler.config import get_butler_home
        from butler.ops.assistant_health import _read_audit_jsonl, _read_audit_metric
        from butler.ops.eval_diagnostics import regression_audit_path

        metrics: dict[str, float] = {}
        sources: dict[str, str] = {}
        audit = get_butler_home() / "audit"
        last = _read_audit_jsonl(regression_audit_path())
        if last:
            metrics["dev_pass_rate"] = round(float(last.get("dev_pass_rate") or 0.0), 4)
            metrics["memory_pass_rate"] = round(float(last.get("mem_pass_rate") or 0.0), 4)
            sources["regression_audit"] = str(regression_audit_path())
        corp = _read_audit_metric(audit / "wechat_corpus_eval.jsonl", "pass_rate")
        if corp is not None:
            metrics["wechat_pass_rate"] = round(corp, 4)
            sources["wechat_corpus_audit"] = str(audit / "wechat_corpus_eval.jsonl")
        return metrics, sources

    result = safe_best_effort(
        _run,
        label="assistant_health.audit_metrics",
        default=({}, {}),
    )
    if isinstance(result, tuple) and len(result) == 2:
        metrics, sources = result
        if isinstance(metrics, dict) and isinstance(sources, dict):
            return dict(metrics), dict(sources)
    return {}, {}

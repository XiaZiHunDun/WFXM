"""LangFuse eval sink best-effort helpers (P0-A)."""

from __future__ import annotations

from butler.contracts.eval_ports import SuiteRunResult


def push_langfuse_suite_scores_safe(result: SuiteRunResult) -> str:
    try:
        from butler.ops.eval_bridge import EvalScore, push_scores

        rate = result.metrics.get("trajectory_compliance_rate")
        if rate is None:
            rate = result.metrics.get("pass_rate")
        if rate is None:
            dev = result.metrics.get("dev_pass_rate")
            mem = result.metrics.get("mem_pass_rate")
            if dev is not None and mem is not None:
                rate = (float(dev) + float(mem)) / 2.0
        if rate is None:
            return ""
        scores = [
            EvalScore(
                name=f"unified.{result.suite_id}",
                value=float(rate),
                comment=f"suite={result.suite_id}",
            )
        ]
        push_scores(scores)
        return "langfuse:scores"
    except Exception:
        return ""

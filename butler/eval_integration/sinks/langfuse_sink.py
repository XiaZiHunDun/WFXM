"""LangFuse sink — wraps eval_bridge when enabled."""

from __future__ import annotations

from typing import Any

from butler.contracts.eval_ports import SuiteRunResult


class LangFuseSink:
    backend_id = "langfuse"

    def write_suite_result(self, result: SuiteRunResult, payload: dict[str, Any]) -> str:
        try:
            from butler.ops.eval_bridge import EvalScore, push_scores

            rate = result.metrics.get("trajectory_compliance_rate")
            if rate is None:
                return ""
            scores = [
                EvalScore(
                    name="tcr_unified",
                    value=float(rate),
                    comment=f"suite={result.suite_id}",
                )
            ]
            push_scores(scores)
            return "langfuse:scores"
        except Exception:
            return ""

    def read_latest(self, suite_id: str) -> dict[str, Any] | None:
        return None

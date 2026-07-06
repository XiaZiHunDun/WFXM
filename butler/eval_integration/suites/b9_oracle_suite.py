"""B9 oracle delegate benchmark suite (O9)."""

from __future__ import annotations

import os

from butler.contracts.eval_ports import SuiteRunResult
from butler.env_parse import float_env


def _min_b9_pass_rate() -> float:
    try:
        return float(float_env("BUTLER_EVAL_B9_PASS_RATE_MIN", 1.0))
    except ValueError:
        return 1.0


class B9OracleSuite:
    suite_id = "b9_oracle"
    layer = "L-D"

    def run(
        self,
        *,
        warn_only: bool = False,
        sync_dataset: bool = False,
        push_langfuse: bool | None = None,
    ) -> SuiteRunResult:
        from butler.dev_engine.b9_types import B9Mode
        from butler.dev_engine.llm_delegate_benchmark import run_llm_delegate_benchmarks
        from butler.ops.eval_diagnostics import append_b9_audit

        if push_langfuse is None:
            push_langfuse = os.getenv("BUTLER_LANGFUSE_ENABLED", "0").strip() in (
                "1",
                "true",
                "yes",
            )
        report = run_llm_delegate_benchmarks(mode=B9Mode.ORACLE)
        append_b9_audit(report)
        threshold = _min_b9_pass_rate()
        ok = report.total == 0 or report.pass_rate >= threshold
        if push_langfuse:
            from butler.eval_integration.suites_ops import push_b9_oracle_scores_safe

            push_b9_oracle_scores_safe(report)
        if warn_only and not ok:
            ok = True
        failures = [r.task_id for r in report.results if not r.passed]
        return SuiteRunResult(
            suite_id=self.suite_id,
            ok=ok,
            layer=self.layer,
            metrics={
                "pass_rate": round(report.pass_rate, 4),
                "passed": report.passed,
                "total": report.total,
                "mode": report.mode,
                "threshold": threshold,
            },
            error="" if ok else f"b9 failures: {', '.join(failures[:3])}",
        )

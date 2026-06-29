"""O7 DevEngine + Memory regression suite."""

from __future__ import annotations

import os

from butler.contracts.eval_ports import SuiteRunResult


class RegressionSuite:
    suite_id = "regression"
    layer = "L-D"

    def run(
        self,
        *,
        warn_only: bool = False,
        sync_dataset: bool = False,
        push_langfuse: bool | None = None,
    ) -> SuiteRunResult:
        from butler.ops.eval_regression import run_regression_gate

        if push_langfuse is None:
            push_langfuse = os.getenv("BUTLER_LANGFUSE_ENABLED", "0").strip() in (
                "1",
                "true",
                "yes",
            )
        report = run_regression_gate(
            push_langfuse=push_langfuse,
            sync_dataset=sync_dataset,
        )
        ok = report.passed
        return SuiteRunResult(
            suite_id=self.suite_id,
            ok=ok,
            layer=self.layer,
            metrics={
                "dev_pass_rate": report.dev_pass_rate,
                "mem_pass_rate": report.mem_pass_rate,
                "b9_pass_rate": report.b9_pass_rate,
                "scores_pushed": report.scores_pushed,
                "dataset_synced": report.dataset_synced,
            },
            error="" if ok else "; ".join(report.failures[:3]),
        )

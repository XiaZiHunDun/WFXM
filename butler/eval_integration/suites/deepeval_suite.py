"""DeepEval agent metrics suite (opt-in, MOD-8)."""

from __future__ import annotations

from butler.contracts.eval_ports import SuiteRunResult
from butler.eval_integration.oss.deepeval_runner import deepeval_available, run_deepeval_agent


class DeepEvalAgentSuite:
    suite_id = "deepeval_agent"
    layer = "L-D"

    def run(
        self,
        *,
        warn_only: bool = False,
        sync_dataset: bool = False,
        push_langfuse: bool | None = None,
    ) -> SuiteRunResult:
        if not deepeval_available():
            return SuiteRunResult(
                suite_id=self.suite_id,
                ok=True,
                layer=self.layer,
                metrics={"skipped": True, "reason": "deepeval not installed"},
            )
        ok, metrics = run_deepeval_agent(warn_only=warn_only)
        return SuiteRunResult(
            suite_id=self.suite_id,
            ok=ok,
            layer=self.layer,
            metrics=metrics,
        )

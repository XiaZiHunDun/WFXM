"""RAGAS memory faithfulness suite (opt-in, MOD-8)."""

from __future__ import annotations

from butler.contracts.eval_ports import SuiteRunResult
from butler.eval_integration.oss.ragas_runner import ragas_available, run_ragas_memory


class RagasMemorySuite:
    suite_id = "ragas_memory"
    layer = "L-D"

    def run(
        self,
        *,
        warn_only: bool = False,
        sync_dataset: bool = False,
        push_langfuse: bool | None = None,
    ) -> SuiteRunResult:
        if not ragas_available():
            return SuiteRunResult(
                suite_id=self.suite_id,
                ok=True,
                layer=self.layer,
                metrics={"skipped": True, "reason": "ragas not installed"},
            )
        ok, metrics = run_ragas_memory(warn_only=warn_only)
        return SuiteRunResult(
            suite_id=self.suite_id,
            ok=ok,
            layer=self.layer,
            metrics=metrics,
        )

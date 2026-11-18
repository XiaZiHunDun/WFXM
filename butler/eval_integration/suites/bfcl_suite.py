"""BFCL v4 simple tool-calling external anchor (opt-in)."""

from __future__ import annotations

from butler.contracts.eval_ports import SuiteRunResult
from butler.eval_integration.oss.bfcl_runner import bfcl_available, run_bfcl_tool_eval


class BfclToolSuite:
    suite_id = "bfcl_tool"
    layer = "L-D"

    def run(
        self,
        *,
        warn_only: bool = False,
        sync_dataset: bool = False,
        push_langfuse: bool | None = None,
    ) -> SuiteRunResult:
        if not bfcl_available():
            return SuiteRunResult(
                suite_id=self.suite_id,
                ok=True,
                layer=self.layer,
                metrics={"skipped": True, "reason": "MINIMAX_* not configured"},
            )
        ok, metrics = run_bfcl_tool_eval(warn_only=warn_only)
        return SuiteRunResult(
            suite_id=self.suite_id,
            ok=ok,
            layer=self.layer,
            metrics=metrics,
        )

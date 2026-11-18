"""Terminal-Bench subset external anchor (opt-in)."""

from __future__ import annotations

from butler.contracts.eval_ports import SuiteRunResult
from butler.eval_integration.oss.terminal_bench_runner import (
    run_terminal_bench_eval,
    terminal_bench_available,
)


class TerminalBenchSuite:
    suite_id = "terminal_bench"
    layer = "L-D"

    def run(
        self,
        *,
        warn_only: bool = False,
        sync_dataset: bool = False,
        push_langfuse: bool | None = None,
    ) -> SuiteRunResult:
        if not terminal_bench_available():
            return SuiteRunResult(
                suite_id=self.suite_id,
                ok=True,
                layer=self.layer,
                metrics={"skipped": True, "reason": "tb 未安装或 Docker 不可用"},
            )
        ok, metrics = run_terminal_bench_eval(warn_only=warn_only)
        return SuiteRunResult(
            suite_id=self.suite_id,
            ok=ok,
            layer=self.layer,
            metrics=metrics,
        )

"""Hermes P0/P1 pytest gate suite."""

from __future__ import annotations

from butler.contracts.eval_ports import SuiteRunResult


class HermesGateSuite:
    suite_id = "hermes_gate"
    layer = "L-D"

    def run(
        self,
        *,
        warn_only: bool = False,
        sync_dataset: bool = False,
        push_langfuse: bool | None = None,
    ) -> SuiteRunResult:
        del sync_dataset, push_langfuse
        from butler.ops.hermes_gate import run_hermes_gate

        report = run_hermes_gate()
        ok = report.passed
        if warn_only and not ok:
            ok = True
        return SuiteRunResult(
            suite_id=self.suite_id,
            ok=ok,
            layer=self.layer,
            metrics={"cases": len(report.failures) if not report.passed else 0},
            error="" if ok else "; ".join(report.failures[:3]),
        )


__all__ = ["HermesGateSuite"]

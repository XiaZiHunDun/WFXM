"""TCR trajectory compliance suite."""

from __future__ import annotations

import json
from pathlib import Path

from butler.contracts.eval_ports import SuiteRunResult

ROOT = Path(__file__).resolve().parents[3]


class TcrSuite:
    suite_id = "tcr"
    layer = "L-B"

    def run(
        self,
        *,
        warn_only: bool = False,
        sync_dataset: bool = False,
        push_langfuse: bool | None = None,
    ) -> SuiteRunResult:
        from butler.ops import tcr_report

        argv = ["--warn-only"] if warn_only else []
        code = tcr_report.main(argv)
        report_path = ROOT / ".butler" / "reports" / "tcr-latest.json"
        metrics: dict = {}
        if report_path.is_file():
            metrics = json.loads(report_path.read_text(encoding="utf-8"))
        ok = code == 0
        return SuiteRunResult(
            suite_id=self.suite_id,
            ok=ok,
            layer=self.layer,
            metrics={
                "trajectory_compliance_rate": metrics.get("trajectory_compliance_rate"),
                "passed": metrics.get("passed"),
                "total": metrics.get("total"),
            },
            sink_refs={"junit": str(report_path)} if report_path.is_file() else {},
            error="" if ok else "TCR below threshold",
        )

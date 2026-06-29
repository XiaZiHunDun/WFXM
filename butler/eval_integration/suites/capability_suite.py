"""Capability baseline suite (quarterly read/delegate/workflow)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from butler.contracts.eval_ports import SuiteRunResult

ROOT = Path(__file__).resolve().parents[3]


class CapabilitySuite:
    suite_id = "capability"
    layer = "L-D"

    def run(
        self,
        *,
        warn_only: bool = False,
        sync_dataset: bool = False,
        push_langfuse: bool | None = None,
    ) -> SuiteRunResult:
        script = ROOT / "scripts" / "butler-capability-baseline.sh"
        proc = subprocess.run(
            ["bash", str(script)],
            cwd=str(ROOT),
            env={**__import__("os").environ, "PYTHONPATH": str(ROOT)},
        )
        report_path = ROOT / ".butler" / "reports" / "capability-baseline.json"
        metrics: dict = {}
        if report_path.is_file():
            metrics = json.loads(report_path.read_text(encoding="utf-8"))
        ok = proc.returncode == 0
        return SuiteRunResult(
            suite_id=self.suite_id,
            ok=ok,
            layer=self.layer,
            metrics={"ok": metrics.get("ok"), "components": metrics.get("components")},
            error="" if ok else "capability baseline failed",
        )

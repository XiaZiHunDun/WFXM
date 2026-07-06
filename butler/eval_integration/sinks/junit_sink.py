"""JUnit / TCR report sink."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from butler.contracts.eval_ports import SuiteRunResult

ROOT = Path(__file__).resolve().parents[3]
TCR_REPORT = ROOT / ".butler" / "reports" / "tcr-latest.json"


class JUnitSink:
    backend_id = "junit"

    def write_suite_result(self, result: SuiteRunResult, payload: dict[str, Any]) -> str:
        if result.suite_id != "tcr":
            return ""
        if TCR_REPORT.is_file():
            return str(TCR_REPORT)
        return ""

    def read_latest(self, suite_id: str) -> dict[str, Any] | None:
        if suite_id != "tcr" or not TCR_REPORT.is_file():
            return None
        data = json.loads(TCR_REPORT.read_text(encoding="utf-8"))
        return cast(dict[str, Any], data) if isinstance(data, dict) else None

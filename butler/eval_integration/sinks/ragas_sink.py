"""Optional RAGAS sink (MOD-8)."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from butler.contracts.eval_ports import SuiteRunResult

ROOT = Path(__file__).resolve().parents[3]


class RagasSink:
    backend_id = "ragas"

    def _path(self) -> Path:
        return ROOT / ".butler" / "reports" / "ragas-latest.json"

    def write_suite_result(self, result: SuiteRunResult, payload: dict[str, Any]) -> str:
        if result.suite_id != "ragas_memory":
            return ""
        path = self._path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "metrics": result.metrics,
                    "ok": result.ok,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return str(path)

    def read_latest(self, suite_id: str) -> dict[str, Any] | None:
        if suite_id != "ragas_memory" or not self._path().is_file():
            return None
        return json.loads(self._path().read_text(encoding="utf-8"))

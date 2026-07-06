"""Local audit jsonl sink."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from butler.contracts.eval_ports import SuiteRunResult


class AuditSink:
    backend_id = "audit"

    def _path(self) -> Path:
        from butler.config import get_butler_home

        return Path(get_butler_home()) / "audit" / "eval_unified.jsonl"

    def write_suite_result(self, result: SuiteRunResult, payload: dict[str, Any]) -> str:
        path = self._path()
        path.parent.mkdir(parents=True, exist_ok=True)
        row = {
            "ts": time.time(),
            "suite_id": result.suite_id,
            "ok": result.ok,
            "layer": result.layer,
            "metrics": result.metrics,
            "payload": payload,
        }
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        return str(path)

    def read_latest(self, suite_id: str) -> dict[str, Any] | None:
        path = self._path()
        if not path.is_file():
            return None
        last: dict[str, Any] | None = None
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
                if row.get("suite_id") == suite_id:
                    last = row
            except json.JSONDecodeError:
                continue
        return last

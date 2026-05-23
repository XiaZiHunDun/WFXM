"""Write corpus live-run records for issue-map analysis."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_CORPUS_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_RUNS_DIR = _CORPUS_ROOT / "archive" / "runs"


def archive_enabled() -> bool:
    return os.getenv("CORPUS_ARCHIVE", "").strip() in ("1", "true", "yes")


def append_run_record(
    *,
    suite_id: str,
    case_id: str,
    dimension: str,
    status: str,
    fail_type: str | None = None,
    note: str = "",
    model: str = "",
    loop_status: str = "",
    response_excerpt: str = "",
    runs_dir: Path | None = None,
) -> Path | None:
    if not archive_enabled():
        return None
    runs_dir = runs_dir or _DEFAULT_RUNS_DIR
    runs_dir.mkdir(parents=True, exist_ok=True)
    run_id = os.getenv("CORPUS_RUN_ID") or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    path = runs_dir / f"{run_id}.jsonl"
    row: dict[str, Any] = {
        "run_id": run_id,
        "suite_id": suite_id,
        "case_id": case_id,
        "dimension": dimension,
        "status": status,
        "fail_type": fail_type,
        "note": note,
        "model": model,
        "loop_status": loop_status,
        "response_excerpt": (response_excerpt or "")[:500],
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return path


def classify_fail(
    *,
    loop_status: str,
    passed: bool,
    keyword_error: str | None = None,
) -> str | None:
    if passed:
        return None
    if keyword_error:
        return "keyword_miss"
    if loop_status == "tool_limit":
        return "tool_limit"
    if loop_status and loop_status != "completed":
        return loop_status
    return "unknown"

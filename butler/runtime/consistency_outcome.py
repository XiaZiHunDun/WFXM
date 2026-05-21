"""Map consistency-check subprocess exit codes to runtime success (P0 gate)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from butler.runtime.schema import JobDef

_P0_LINE = re.compile(r"P0:\s*(\d+)", re.IGNORECASE)
_P1_LINE = re.compile(r"P1:\s*(\d+)", re.IGNORECASE)


def _p0_p1_from_stdout(stdout: str) -> tuple[int | None, int | None]:
    p0 = p1 = None
    m0 = _P0_LINE.search(stdout or "")
    m1 = _P1_LINE.search(stdout or "")
    if m0:
        p0 = int(m0.group(1))
    if m1:
        p1 = int(m1.group(1))
    return p0, p1


def _p0_p1_from_json_report(path: Path) -> tuple[int | None, int | None]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None, None
    by = data.get("by_severity") or {}
    if not isinstance(by, dict):
        return None, None
    return int(by.get("P0", 0)), int(by.get("P1", 0))


def apply_consistency_success_policy(
    job: JobDef,
    workspace: Path,
    result: dict[str, Any],
) -> dict[str, Any]:
    """
    consistency-weekly: exit 1 with only P1 issues still counts as runtime success.

    Subprocess may exit 1 when P1>0; we treat P0==0 as passed (optionally with warnings).
    """
    if job.id != "consistency-weekly":
        return result

    p0, p1 = _p0_p1_from_stdout(str(result.get("stdout") or ""))
    if p0 is None:
        for raw in result.get("report_paths") or []:
            jp = Path(raw)
            if not jp.is_absolute():
                jp = (workspace / jp).resolve()
            if jp.suffix == ".json" and jp.is_file():
                p0, p1 = _p0_p1_from_json_report(jp)
                if p0 is not None:
                    break

    if p0 is None:
        return result

    rc = int(result.get("returncode") or 0)
    if p0 == 0 and rc != 0:
        out = dict(result)
        out["success"] = True
        out["outcome"] = "passed_with_warnings" if (p1 or 0) > 0 else "passed"
        note = f"一致性检查 P0=0"
        if (p1 or 0) > 0:
            note += f"，P1={p1}（有条件通过）"
        summary = (out.get("summary") or "").strip()
        if note not in summary:
            out["summary"] = f"{summary}\n\n{note}".strip() if summary else note
        return out

    if p0 > 0:
        out = dict(result)
        out["success"] = False
        out["outcome"] = "failed_p0"
        return out

    return result

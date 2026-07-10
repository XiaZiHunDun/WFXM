"""Consistency weekly report summarizer for WeChat push (P2 #9).

Read-only collector over `novel-factory/tools/consistency/consistency_check_report.json`.
Returns normalized data + verdict; never writes.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_REPORT_REL = Path("novel-factory") / "tools" / "consistency" / "consistency_check_report.json"
_CHECK_NAMES = ("naming", "integrity", "duplicates", "character", "timeline")
# P1 抽样优先级：character (ALIVE_CONFLICT 主源) > timeline > integrity > naming > duplicates
_CHECK_PRIORITY = ("character", "timeline", "integrity", "naming", "duplicates")
_TOP_P1_CAP = 5


def _age_days(started_at: str) -> float | None:
    if not started_at:
        return None
    try:
        dt = datetime.fromisoformat(started_at)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - dt
    return round(delta.total_seconds() / 86400.0, 2)


def _safe_load(path: Path) -> tuple[bool, str | None, dict | None]:
    if not path.is_file():
        return False, f"missing report: {path}", None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return False, f"read failed: {exc}", None
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return False, f"json decode failed: {exc}", None
    if not isinstance(data, dict):
        return False, "top-level is not an object", None
    return True, None, data


def _flatten_p1_details(checks: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for check_name in _CHECK_PRIORITY:
        block = checks.get(check_name) if isinstance(checks, dict) else None
        if not isinstance(block, dict):
            continue
        details = block.get("details")
        if not isinstance(details, list):
            continue
        for row in details:
            if not (isinstance(row, (list, tuple)) and len(row) >= 4):
                continue
            issue_type, chapter, entity, message = row[0], row[1], row[2], row[3]
            out.append({
                "check": check_name,
                "issue_type": str(issue_type or ""),
                "chapter": int(chapter) if isinstance(chapter, (int, float)) else 0,
                "entity": str(entity or ""),
                "message": str(message or ""),
            })
    return out[:_TOP_P1_CAP]


def summarize_consistency_report(workspace: Path) -> dict[str, Any]:
    """Read the consistency JSON and produce a normalized summary envelope.

    Returns:
        dict with `loaded` (bool). When False, only `path`/`error` are meaningful
        and verdict defaults to "pass" so a missing report does not false-alarm.
    """
    path = workspace / _REPORT_REL
    ok, error, raw = _safe_load(path)
    if not ok or raw is None:
        return {
            "loaded": False,
            "path": str(path),
            "error": error or "unknown",
            "verdict": "pass",
        }

    by_severity = raw.get("by_severity") if isinstance(raw.get("by_severity"), dict) else {}
    p0 = int(by_severity.get("P0") or 0)
    p1 = int(by_severity.get("P1") or 0)
    p2 = int(by_severity.get("P2") or 0)
    total = int(raw.get("total_issues") or (p0 + p1 + p2))

    checks = raw.get("checks") if isinstance(raw.get("checks"), dict) else {}
    by_check = {name: int((checks.get(name) or {}).get("issues") or 0) for name in _CHECK_NAMES}

    if p0 > 0:
        verdict = "fail"
    elif p1 > 0:
        verdict = "warn"
    else:
        verdict = "pass"

    return {
        "loaded": True,
        "path": str(path),
        "error": None,
        "chapter_range": str(raw.get("chapter_range") or "?"),
        "started_at": str(raw.get("started_at") or ""),
        "duration_seconds": float(raw.get("duration_seconds") or 0.0),
        "age_days": _age_days(str(raw.get("started_at") or "")),
        "totals": {"P0": p0, "P1": p1, "P2": p2, "total": total},
        "by_check": by_check,
        "top_p1": _flatten_p1_details(checks),
        "verdict": verdict,
    }

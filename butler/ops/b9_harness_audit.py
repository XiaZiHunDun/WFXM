"""B9 harness friction audit — READ_STATE / TOOL_ERROR trends from delegate audit."""

from __future__ import annotations

import json
import re
import time
from collections import Counter
from pathlib import Path
from typing import Any


def _audit_paths() -> tuple[Path, Path]:
    from butler.config import get_butler_home

    home = get_butler_home() / "audit"
    return home / "delegate_failures.jsonl", home / "b9_lessons.jsonl"


def _is_b9_row(rec: dict[str, Any]) -> bool:
    preview = str(rec.get("task_preview") or "")
    category = str(rec.get("category") or "")
    return (
        "b9-benchmark" in preview
        or "B9L" in preview
        or category == "b9-benchmark"
    )


_READ_STATE_CODES = (
    "READ_STATE_REQUIRED",
    "READ_STATE_PARTIAL_VIEW",
    "READ_STATE_STALE",
    "READ_STATE_NOT_FILE",
    "READ_STATE_STAT_FAILED",
)


def _extract_read_state_codes(blob: str) -> list[str]:
    codes: list[str] = []
    for code in _READ_STATE_CODES:
        if code in blob:
            codes.append(code)
    if "必须先调用 read_file" in blob and "READ_STATE_REQUIRED" not in codes:
        codes.append("READ_STATE_REQUIRED")
    return codes


def summarize_harness_friction(
    *,
    limit: int = 300,
    min_count: int = 1,
) -> dict[str, Any]:
    """Summarize B9 harness friction from delegate_failures + recent lessons."""
    failures_path, lessons_path = _audit_paths()
    read_state: Counter[str] = Counter()
    tool_errors: Counter[str] = Counter()
    total_b9 = 0

    if failures_path.is_file():
        for line in failures_path.read_text(encoding="utf-8").splitlines()[-limit:]:
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not _is_b9_row(rec):
                continue
            total_b9 += 1
            issues = rec.get("issues") or []
            blob = " ".join(str(i) for i in issues) + " " + str(rec.get("failure_reason") or "")
            for code in _extract_read_state_codes(blob):
                read_state[code] += 1
            if "TOOL_ERROR" in blob or "tool error" in blob.lower():
                tool_errors["TOOL_ERROR"] += 1
            sig_m = re.search(r"code:\s*([A-Z0-9_]+)", blob)
            if sig_m and sig_m.group(1).startswith("READ_STATE"):
                read_state[sig_m.group(1)] += 1

    lesson_read_state = 0
    if lessons_path.is_file():
        for line in lessons_path.read_text(encoding="utf-8").splitlines()[-limit:]:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            tail = str(row.get("failure_tail") or row.get("lesson") or "")
            if _extract_read_state_codes(tail):
                lesson_read_state += 1

    from butler.ops.b9_harness_audit_ops import mine_delegate_failure_signatures_safe

    mined = mine_delegate_failure_signatures_safe(limit=limit, min_count=min_count)

    return {
        "delegate_failures_b9_rows": total_b9,
        "read_state_by_code": dict(read_state.most_common()),
        "read_state_total": sum(read_state.values()),
        "tool_error_total": sum(tool_errors.values()),
        "lessons_with_read_state_hint": lesson_read_state,
        "top_signatures": mined.get("signatures") or [],
        "audit_path": str(failures_path),
        "lessons_path": str(lessons_path),
    }


_SNAPSHOTS_NAME = "b9_harness_snapshots.jsonl"


def harness_snapshots_path() -> Path:
    from butler.config import get_butler_home

    return get_butler_home() / "audit" / _SNAPSHOTS_NAME


def record_harness_friction_snapshot() -> dict[str, Any]:
    """Append current friction summary and return week-over-week delta."""
    summary = summarize_harness_friction()
    summary["recorded_at"] = time.time()
    path = harness_snapshots_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(summary, ensure_ascii=False) + "\n")
    summary["delta"] = compare_harness_friction_delta()
    return summary


def compare_harness_friction_delta(*, keep: int = 2) -> dict[str, Any]:
    """Delta between the last two harness snapshots (A3 weekly trend)."""
    path = harness_snapshots_path()
    if not path.is_file():
        return {"snapshots": 0}
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    if len(rows) < 2:
        return {"snapshots": len(rows), "note": "need 2+ snapshots for delta"}
    prev, cur = rows[-2], rows[-1]
    return {
        "snapshots": len(rows),
        "read_state_total_delta": int(cur.get("read_state_total", 0))
        - int(prev.get("read_state_total", 0)),
        "tool_error_total_delta": int(cur.get("tool_error_total", 0))
        - int(prev.get("tool_error_total", 0)),
        "prev_recorded_at": prev.get("recorded_at"),
        "cur_recorded_at": cur.get("recorded_at"),
    }


def format_harness_friction_delta(delta: dict[str, Any] | None) -> str:
    if not delta or delta.get("snapshots", 0) < 2:
        return "harness_delta=(insufficient snapshots)"
    return (
        "harness_delta="
        f"read_state {delta.get('read_state_total_delta', 0):+d}, "
        f"tool_error {delta.get('tool_error_total_delta', 0):+d}"
    )


def format_harness_friction_report(summary: dict[str, Any] | None = None) -> str:
    data = summary if summary is not None else summarize_harness_friction()
    lines = [
        "=== B9 harness friction ===",
        f"delegate_failures_b9_rows={data.get('delegate_failures_b9_rows', 0)}",
        f"read_state_total={data.get('read_state_total', 0)}",
        f"read_state_by_code={data.get('read_state_by_code', {})}",
        f"tool_error_total={data.get('tool_error_total', 0)}",
        f"lessons_with_read_state_hint={data.get('lessons_with_read_state_hint', 0)}",
    ]
    sigs = data.get("top_signatures") or []
    if sigs:
        lines.append("top_signatures=" + ", ".join(f"{s['signature']}:{s['count']}" for s in sigs[:8]))
    return "\n".join(lines)


__all__ = [
    "compare_harness_friction_delta",
    "format_harness_friction_delta",
    "format_harness_friction_report",
    "harness_snapshots_path",
    "record_harness_friction_snapshot",
    "summarize_harness_friction",
]

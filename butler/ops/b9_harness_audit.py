"""B9 harness friction audit — READ_STATE / TOOL_ERROR trends from delegate audit."""

from __future__ import annotations

import json
import re
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

    mined = {}
    try:
        from butler.ops.b9_failure_analysis import mine_delegate_failure_signatures

        mined = mine_delegate_failure_signatures(limit=limit, min_count=min_count)
    except Exception:
        pass

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
    "format_harness_friction_report",
    "summarize_harness_friction",
]

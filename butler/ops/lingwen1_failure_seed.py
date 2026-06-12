"""Seed LingWen1-shaped production delegate failures into audit (once each)."""

from __future__ import annotations

import time
from typing import Any

LINGWEN1_AUDIT_RECORD: dict[str, Any] = {
    "role": "dev",
    "task_id": "lingwen1-demo-add-fix",
    "trace_id": "trace-lingwen1-demo-add-001",
    "project": "LingWen1",
    "failure_reason": "verify_fail",
    "task_preview": (
        "Fix demo/hello.py in LingWen1: add(a, b) must return a + b. "
        "test_b9.py expects add(3.5, 4.5) == 8.0. Only edit demo/hello.py."
    ),
    "issues": ["pytest failed: assert -1.0 == 8.0"],
    "verify_passed": False,
    "demo": False,
    "capture_source": "seed",
}

LINGWEN1_VALIDATE_AUDIT_RECORD: dict[str, Any] = {
    "role": "dev",
    "task_id": "lingwen1-workflow-guard-fix",
    "trace_id": "trace-lingwen1-workflow-guard-001",
    "project": "LingWen1",
    "failure_reason": "verify_fail",
    "task_preview": (
        "Fix scripts/workflow_guard.py in LingWen1 novel-factory workspace: "
        "has_open_completed() must return True when completed batch result contains 待修复. "
        "test_b9.py must pass. Only edit scripts/workflow_guard.py."
    ),
    "issues": ["pytest failed: assert False is True"],
    "verify_passed": False,
    "demo": False,
    "capture_source": "seed",
}

LINGWEN1_AUDIT_RECORDS: tuple[dict[str, Any], ...] = (
    LINGWEN1_AUDIT_RECORD,
    LINGWEN1_VALIDATE_AUDIT_RECORD,
)


def _audit_task_ids() -> set[str]:
    from butler.ops.delegate_failure_capture import failure_audit_summary

    ids: set[str] = set()
    for rec in failure_audit_summary(limit=500).get("recent") or []:
        tid = str(rec.get("task_id") or "").strip()
        if tid:
            ids.add(tid)
    return ids


def lingwen1_audit_present(*, task_id: str = "") -> bool:
    """True if a specific LingWen1 seed row (or any LingWen1 row) is already in audit."""
    ids = _audit_task_ids()
    if task_id:
        return task_id in ids
    return any(tid in ids for tid in (r["task_id"] for r in LINGWEN1_AUDIT_RECORDS))


def seed_lingwen1_failure_audit(*, force: bool = False) -> dict[str, Any]:
    """Append missing LingWen1-shaped failure rows."""
    from butler.ops.delegate_failure_capture import _append_audit, failure_audit_summary

    seeded: list[str] = []
    skipped: list[str] = []
    for template in LINGWEN1_AUDIT_RECORDS:
        tid = str(template["task_id"])
        if tid in _audit_task_ids() and not force:
            skipped.append(tid)
            continue
        record = {**template, "ts": time.time()}
        _append_audit(record)
        seeded.append(tid)
    return {
        "seeded": seeded,
        "skipped": skipped,
        "audit_path": failure_audit_summary().get("audit_path"),
    }


__all__ = [
    "LINGWEN1_AUDIT_RECORD",
    "LINGWEN1_AUDIT_RECORDS",
    "LINGWEN1_VALIDATE_AUDIT_RECORD",
    "lingwen1_audit_present",
    "seed_lingwen1_failure_audit",
]

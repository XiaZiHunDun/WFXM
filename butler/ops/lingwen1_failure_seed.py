"""Seed a LingWen1-shaped production delegate failure into audit (once)."""

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
}


def lingwen1_audit_present() -> bool:
    from butler.ops.delegate_failure_capture import failure_audit_summary

    for rec in failure_audit_summary(limit=500).get("recent") or []:
        if str(rec.get("task_id") or "") == LINGWEN1_AUDIT_RECORD["task_id"]:
            return True
        if "lingwen1" in str(rec.get("task_preview") or "").lower():
            return True
        if str(rec.get("project") or "") == "LingWen1":
            return True
    return False


def seed_lingwen1_failure_audit(*, force: bool = False) -> dict[str, Any]:
    """Append LingWen1 demo/add failure row if not already captured."""
    if lingwen1_audit_present() and not force:
        return {
            "seeded": False,
            "reason": "already_present",
            "task_id": LINGWEN1_AUDIT_RECORD["task_id"],
        }
    from butler.ops.delegate_failure_capture import _append_audit, failure_audit_summary

    record = {**LINGWEN1_AUDIT_RECORD, "ts": time.time()}
    _append_audit(record)
    return {
        "seeded": True,
        "task_id": record["task_id"],
        "audit_path": failure_audit_summary().get("audit_path"),
    }


__all__ = [
    "LINGWEN1_AUDIT_RECORD",
    "lingwen1_audit_present",
    "seed_lingwen1_failure_audit",
]

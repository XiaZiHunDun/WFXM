"""Exercise LingWen1 production failure capture through delegate_failure_capture."""

from __future__ import annotations

import time
from typing import Any

PROBE_TASK_ID = "lingwen1-live-capture-demo-add"
PROBE_TRACE_ID = "trace-lingwen1-live-capture-001"

LINGWEN1_CAPTURE_PROBE_TASK = (
    "Fix projects/LingWen1/demo/hello.py: add(a, b) must return a + b. "
    "pytest in workspace expects add(3.5, 4.5) == 8.0. Only edit demo/hello.py."
)


def lingwen1_live_capture_present() -> bool:
    from butler.ops.delegate_failure_capture import failure_audit_summary

    for rec in failure_audit_summary(limit=500).get("recent") or []:
        if str(rec.get("task_id") or "") == PROBE_TASK_ID:
            return True
        if str(rec.get("capture_source") or "") == "delegate_probe":
            return True
    return False


def run_lingwen1_capture_probe(*, force: bool = False) -> dict[str, Any]:
    """Simulate a post-delegate LingWen1 verify_fail through the capture pipeline."""
    from butler.ops.delegate_failure_capture import capture_delegate_failure, capture_enabled

    if not capture_enabled():
        return {
            "captured": False,
            "reason": "capture_disabled",
            "hint": "Set BUTLER_EVAL_CAPTURE_DELEGATE_FAILURES=1",
        }
    if lingwen1_live_capture_present() and not force:
        return {
            "captured": False,
            "reason": "already_present",
            "task_id": PROBE_TASK_ID,
        }

    dev_engine = {
        "verify_passed": False,
        "phase": "verify",
        "edits": 1,
        "fixes": 2,
        "experience_lifecycle": {"action": "demoted", "experience_id": "B9_EX_prod_lingwen_demo_add"},
    }
    return capture_delegate_failure(
        role="dev",
        task=LINGWEN1_CAPTURE_PROBE_TASK,
        context="project=LingWen1; workspace=projects/LingWen1",
        success=False,
        issues=["pytest failed: assert -1.0 == 8.0"],
        trace_id=PROBE_TRACE_ID,
        task_id=PROBE_TASK_ID,
        project="LingWen1",
        capture_source="delegate_probe",
        dev_engine=dev_engine,
        failure_reason="verify_fail",
    )


__all__ = [
    "LINGWEN1_CAPTURE_PROBE_TASK",
    "PROBE_TASK_ID",
    "lingwen1_live_capture_present",
    "run_lingwen1_capture_probe",
]

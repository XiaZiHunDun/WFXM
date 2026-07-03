"""Capture production delegate failures into LangFuse Dataset + Scores.

When a dev delegate fails or verify does not pass, writes a sanitized dataset item
to ``butler-delegate-failures`` and score ``delegate_failure`` on the parent trace.
Also appends ``~/.butler/audit/delegate_failures.jsonl`` for weekly annotation.

Opt-in: ``BUTLER_EVAL_CAPTURE_DELEGATE_FAILURES`` (default on when LangFuse enabled).
Set ``all`` to capture non-dev delegate failures too.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DATASET_NAME = "butler-delegate-failures"
_AUDIT_NAME = "delegate_failures.jsonl"

_SECRET_PATTERNS = (
    re.compile(r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*\S+"),
    re.compile(r"(?i)sk-[a-zA-Z0-9]{10,}"),
    re.compile(r"(?i)pk-[a-zA-Z0-9]{10,}"),
)


def _norm_role(role: str) -> str:
    return str(role or "").replace("_agent", "").strip().lower()


def capture_enabled() -> bool:
    raw = os.getenv("BUTLER_EVAL_CAPTURE_DELEGATE_FAILURES", "").strip().lower()
    if raw in ("0", "false", "no"):
        return False
    if raw in ("1", "true", "yes", "all"):
        return True
    from butler.ops.delegate_failure_capture_ops import langfuse_capture_enabled_safe

    return langfuse_capture_enabled_safe()


def _capture_all_roles() -> bool:
    return os.getenv("BUTLER_EVAL_CAPTURE_DELEGATE_FAILURES", "").strip().lower() == "all"


def sanitize_text(text: str, *, limit: int = 2000) -> str:
    """Redact secrets and shorten paths for dataset storage."""
    out = str(text or "")
    home = str(Path.home())
    if home and home in out:
        out = out.replace(home, "~")
    for pat in _SECRET_PATTERNS:
        out = pat.sub("[REDACTED]", out)
    return out[:limit]


def should_capture_failure(
    *,
    role: str,
    success: bool,
    dev_engine: dict[str, Any] | None = None,
) -> bool:
    if not capture_enabled():
        return False
    verify_failed = bool(dev_engine and dev_engine.get("verify_passed") is False)
    if _capture_all_roles():
        return (not success) or verify_failed
    if _norm_role(role) != "dev":
        return False
    return (not success) or verify_failed


def _audit_path() -> Path:
    from butler.config import get_butler_home

    return get_butler_home() / "audit" / _AUDIT_NAME


def _append_audit(record: dict[str, Any]) -> None:
    path = _audit_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def failure_audit_summary(*, limit: int = 200) -> dict[str, Any]:
    """Summarize captured failures from the local audit log."""
    path = _audit_path()
    if not path.is_file():
        return {"total": 0, "by_reason": {}, "recent": []}

    from butler.ops.delegate_failure_capture_ops import read_failure_audit_summary_safe

    total, by_reason, recent = read_failure_audit_summary_safe(path, limit=limit)
    return {
        "total": total,
        "by_reason": by_reason,
        "recent": recent[-10:],
        "audit_path": str(path),
    }


def build_failure_dataset_item(
    *,
    role: str,
    task: str,
    context: str = "",
    issues: list[str] | None = None,
    trace_id: str = "",
    task_id: str = "",
    dev_engine: dict[str, Any] | None = None,
    failure_reason: str = "",
) -> Any:
    from butler.ops.eval_bridge import DatasetItem

    verify_failed = bool(dev_engine and dev_engine.get("verify_passed") is False)
    reason = failure_reason or (
        "verify_failed" if verify_failed else "delegate_failed"
    )
    source_id = task_id or f"fail-{int(time.time())}"
    return DatasetItem(
        input={
            "role": role,
            "task": sanitize_text(task, limit=1200),
            "context": sanitize_text(context, limit=800),
            "failure_reason": reason,
        },
        expected_output={
            "success": False,
            "verify_passed": not verify_failed if dev_engine else None,
        },
        metadata={
            "trace_id": trace_id,
            "task_id": task_id,
            "issues": [sanitize_text(i, limit=300) for i in (issues or [])[:5]],
            "dev_engine": dev_engine or {},
            "captured_at": time.time(),
        },
        source_id=source_id,
    )


def capture_delegate_failure(
    *,
    role: str,
    task: str,
    context: str = "",
    success: bool,
    issues: list[str] | None = None,
    trace_id: str = "",
    task_id: str = "",
    project: str = "",
    capture_source: str = "",
    dev_engine: dict[str, Any] | None = None,
    failure_reason: str = "",
) -> dict[str, Any]:
    """Push a delegate failure to LangFuse dataset + score and local audit."""
    summary: dict[str, Any] = {
        "captured": False,
        "dataset_pushed": False,
        "score_pushed": False,
        "failure_reason": failure_reason or "delegate_failed",
    }
    if not should_capture_failure(role=role, success=success, dev_engine=dev_engine):
        return summary

    verify_failed = bool(dev_engine and dev_engine.get("verify_passed") is False)
    summary["failure_reason"] = failure_reason or (
        "verify_failed" if verify_failed else "delegate_failed"
    )
    summary["captured"] = True

    audit_rec = {
        "ts": time.time(),
        "role": role,
        "task_id": task_id,
        "trace_id": trace_id,
        "failure_reason": summary["failure_reason"],
        "task_preview": sanitize_text(task, limit=200),
        "issues": [sanitize_text(i, limit=200) for i in (issues or [])[:3]],
        "verify_passed": None if dev_engine is None else dev_engine.get("verify_passed"),
    }
    if project:
        audit_rec["project"] = project
    if capture_source:
        audit_rec["capture_source"] = capture_source
    from butler.ops.delegate_failure_capture_ops import append_failure_audit_safe

    append_failure_audit_safe(_audit_path(), audit_rec)

    from butler.ops.delegate_failure_capture_ops import follow_up_production_capture_safe

    summary["experience_followup"] = follow_up_production_capture_safe(
        role=role,
        task=task,
        success=success,
        project=project,
        capture_source=capture_source,
        task_id=task_id,
        task_preview=audit_rec.get("task_preview", ""),
        failure_reason=summary["failure_reason"],
        issues=issues,
        dev_engine=dev_engine,
    )

    from butler.ops.delegate_failure_capture_ops import record_g1_04_evidence_safe

    summary["g1_04_evidence"] = record_g1_04_evidence_safe(
        role=role,
        project=project,
        success=success,
        verify_passed=None if dev_engine is None else dev_engine.get("verify_passed"),
        task_id=task_id,
        task_preview=audit_rec.get("task_preview", ""),
        failure_reason=summary["failure_reason"],
        capture_source=capture_source or "delegate_pipeline",
    )

    from butler.ops.delegate_failure_capture_ops import push_failure_to_langfuse_loud

    dataset_pushed, score_pushed, err = push_failure_to_langfuse_loud(
        role=role,
        task=task,
        context=context,
        issues=issues,
        trace_id=trace_id,
        task_id=task_id,
        dev_engine=dev_engine,
        failure_reason=summary["failure_reason"],
    )
    summary["dataset_pushed"] = dataset_pushed
    summary["score_pushed"] = score_pushed
    if err:
        summary["error"] = err

    return summary


def maybe_capture_from_delegate_result(
    *,
    role: str,
    task: str,
    context: str = "",
    success: bool,
    issues: list[str] | None = None,
    parent_session_key: str = "",
    child_session_key: str = "",
    task_id: str = "",
    project: str = "",
    dev_engine: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve trace id from active delegate/parent context and capture if needed."""
    from butler.ops.delegate_failure_capture_ops import resolve_delegate_trace_id_safe

    trace_id = resolve_delegate_trace_id_safe(
        child_session_key=child_session_key,
        parent_session_key=parent_session_key,
    )

    return capture_delegate_failure(
        role=role,
        task=task,
        context=context,
        success=success,
        issues=issues,
        trace_id=trace_id,
        task_id=task_id,
        project=project,
        capture_source="delegate_pipeline",
        dev_engine=dev_engine,
    )


__all__ = [
    "DATASET_NAME",
    "build_failure_dataset_item",
    "capture_delegate_failure",
    "capture_enabled",
    "failure_audit_summary",
    "maybe_capture_from_delegate_result",
    "sanitize_text",
    "should_capture_failure",
]

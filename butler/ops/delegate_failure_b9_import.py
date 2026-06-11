"""Export production delegate failures as B9 task candidates.

Reads ``~/.butler/audit/delegate_failures.jsonl`` and emits structured stubs
for manual promotion into ``b9_live_fixed_tasks.py`` / ``B9_TASKS``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from butler.ops.delegate_failure_capture import failure_audit_summary


def _slug(text: str, *, max_len: int = 40) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", text.strip().lower()).strip("_")
    return (slug or "case")[:max_len]


def load_failure_records(*, limit: int = 50) -> list[dict[str, Any]]:
    summary = failure_audit_summary(limit=limit)
    return list(summary.get("recent") or [])


def failure_to_b9_candidate(record: dict[str, Any]) -> dict[str, Any]:
    """Map an audit record to a suggested B9TaskSpec-shaped dict."""
    task_preview = str(record.get("task_preview") or record.get("task") or "")
    reason = str(record.get("failure_reason") or "unknown")
    task_id = str(record.get("task_id") or "")
    slug = _slug(task_id or task_preview[:30])
    return {
        "suggested_task_id": f"B9L_prod_{slug}",
        "description": f"Production delegate failure ({reason})",
        "delegate_prompt": task_preview,
        "failure_reason": reason,
        "trace_id": record.get("trace_id", ""),
        "source_task_id": task_id,
        "verify_passed": record.get("verify_passed"),
        "issues": record.get("issues") or [],
        "promotion_checklist": [
            "Add setup() that reproduces workspace from sanitized context",
            "Add verify() with pytest or structural assertion",
            "Add oracle_apply() for CI oracle mode",
            "Append B9TaskSpec to b9_live_fixed_tasks.py or B9_TASKS",
            "Run: PYTHONPATH=. pytest tests/test_b9_live_fixed_tasks.py -q",
        ],
    }


def export_b9_candidates(
    *,
    limit: int = 20,
    out_path: Path | None = None,
) -> dict[str, Any]:
    """Export recent failures as JSON candidate list."""
    records = load_failure_records(limit=limit)
    candidates = [failure_to_b9_candidate(r) for r in records]
    payload = {
        "total": len(candidates),
        "candidates": candidates,
        "audit_path": failure_audit_summary().get("audit_path"),
    }
    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        payload["written"] = str(out_path)
    return payload


__all__ = [
    "export_b9_candidates",
    "failure_to_b9_candidate",
    "load_failure_records",
]

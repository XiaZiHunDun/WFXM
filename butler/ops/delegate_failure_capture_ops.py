"""Delegate failure capture best-effort helpers (P0-A)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from butler.core.best_effort import safe_best_effort

logger = logging.getLogger(__name__)


def langfuse_capture_enabled_safe() -> bool:
    def _run() -> bool:
        from butler.ops.langfuse_tracer import langfuse_enabled

        return bool(langfuse_enabled())

    result = safe_best_effort(_run, label="delegate_failure.langfuse_enabled", default=False)
    return bool(result)


def read_failure_audit_summary_safe(
    path: Path,
    *,
    limit: int,
) -> tuple[int, dict[str, int], list[dict[str, Any]]]:
    def _run() -> tuple[int, dict[str, int], list[dict[str, Any]]]:
        by_reason: dict[str, int] = {}
        recent: list[dict[str, Any]] = []
        total = 0
        lines = path.read_text(encoding="utf-8").splitlines()
        for line in lines[-limit:]:
            if not line.strip():
                continue
            rec = json.loads(line)
            total += 1
            reason = str(rec.get("failure_reason") or "unknown")
            by_reason[reason] = by_reason.get(reason, 0) + 1
            recent.append(rec)
        return total, by_reason, recent

    result = safe_best_effort(
        _run,
        label="delegate_failure.audit_summary",
        default=(0, {}, []),
    )
    if isinstance(result, tuple) and len(result) == 3:
        return int(result[0]), dict(result[1]), list(result[2])
    return 0, {}, []


def append_failure_audit_safe(path: Path, record: dict[str, Any]) -> None:
    def _run() -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    safe_best_effort(_run, label="delegate_failure.audit_append", default=None)


def follow_up_production_capture_safe(**kwargs: Any) -> Any:
    def _run() -> Any:
        from butler.ops.production_failure_experience import follow_up_production_capture

        return follow_up_production_capture(**kwargs)

    return safe_best_effort(_run, label="delegate_failure.experience_followup", default=None)


def record_g1_04_evidence_safe(**kwargs: Any) -> Any:
    def _run() -> Any:
        from butler.ops.g1_04_prod_evidence import record_g1_04_production_evidence

        return record_g1_04_production_evidence(**kwargs)

    return safe_best_effort(_run, label="delegate_failure.g1_04", default=None)


def push_failure_to_langfuse_loud(
    *,
    role: str,
    task: str,
    context: str,
    issues: list[str] | None,
    trace_id: str,
    task_id: str,
    dev_engine: dict[str, Any] | None,
    failure_reason: str,
) -> tuple[bool, bool, str]:
    try:
        from butler.ops.delegate_failure_capture import DATASET_NAME, build_failure_dataset_item
        from butler.ops.eval_bridge import EvalScore, create_dataset, push_dataset_item, push_score

        create_dataset(
            DATASET_NAME,
            "Production dev delegate failures for annotation and B9 expansion",
        )
        item = build_failure_dataset_item(
            role=role,
            task=task,
            context=context,
            issues=issues,
            trace_id=trace_id,
            task_id=task_id,
            dev_engine=dev_engine,
            failure_reason=failure_reason,
        )
        dataset_pushed = push_dataset_item(DATASET_NAME, item)
        score_pushed = False
        if trace_id:
            score_pushed = push_score(
                EvalScore(
                    name="delegate_failure",
                    value=0.0,
                    comment=failure_reason,
                    category="delegate",
                    trace_id=trace_id,
                    metadata={
                        "task_id": task_id,
                        "role": role,
                        "verify_passed": dev_engine.get("verify_passed")
                        if dev_engine
                        else None,
                    },
                )
            )
        return dataset_pushed, score_pushed, ""
    except Exception as exc:
        logger.warning("delegate failure LangFuse capture failed: %s", exc)
        return False, False, str(exc)


def resolve_delegate_trace_id_safe(
    *,
    child_session_key: str,
    parent_session_key: str,
) -> str:
    def _run() -> str:
        from butler.ops.langfuse_tracer import (
            get_current_trace,
            get_delegate_trace,
        )

        delegate_ctx = get_delegate_trace(child_session_key)
        if delegate_ctx is not None:
            return str(delegate_ctx.trace_id or "")
        parent = get_current_trace(parent_session_key)
        if parent is not None:
            return str(parent.trace_id or "")
        return ""

    result = safe_best_effort(_run, label="delegate_failure.trace_id", default="")
    return str(result or "")

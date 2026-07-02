"""Best-effort helpers for delegate report observability (P0-A)."""

from __future__ import annotations

from typing import Any

from butler.core.best_effort import safe_best_effort


def record_acceptance_card_safe(report: Any, *, session_key: str) -> None:
    def _run() -> None:
        from butler.ops.owner_pmf_metrics import record_acceptance_card

        record_acceptance_card(report, session_key=session_key)

    safe_best_effort(_run, label="delegate_report.acceptance_card", default=None)


def finish_delegate_trace_safe(
    session_key: str,
    *,
    success: bool,
    metadata: dict[str, Any],
) -> None:
    def _run() -> None:
        from butler.ops.langfuse_tracer import finish_delegate_trace

        finish_delegate_trace(session_key, success=success, metadata=metadata)

    safe_best_effort(_run, label="delegate_report.langfuse_finish", default=None)


def resolve_delegate_trace_id_safe(
    child_session_key: str,
    parent_session_key: str,
) -> str:
    def _run() -> str:
        from butler.ops.langfuse_tracer import get_current_trace, get_delegate_trace

        trace_id = ""
        delegate_ctx = get_delegate_trace(child_session_key)
        if delegate_ctx is not None:
            trace_id = delegate_ctx.trace_id
        parent = get_current_trace(parent_session_key)
        if not trace_id and parent is not None:
            trace_id = parent.trace_id
        return trace_id

    result = safe_best_effort(
        _run,
        label="delegate_report.trace_lookup",
        default="",
    )
    return str(result or "")


def maybe_judge_delegate_safe(
    *,
    success: bool,
    issues: list[str],
    dev_engine: dict[str, Any] | None,
    task: str,
    summary: str,
    trace_id: str,
) -> None:
    def _run() -> None:
        from butler.ops.delegate_judge import maybe_judge_and_push

        maybe_judge_and_push(
            success=success,
            issues=issues,
            dev_engine=dev_engine,
            task=task,
            summary=summary,
            trace_id=trace_id,
        )

    safe_best_effort(_run, label="delegate_report.judge", default=None)


def maybe_capture_delegate_failure_safe(
    *,
    role: str,
    task: str,
    context: str,
    success: bool,
    issues: list[str],
    parent_session_key: str,
    child_session_key: str,
    task_id: str,
    project: str,
    dev_engine: dict[str, Any] | None,
) -> None:
    def _run() -> None:
        from butler.ops.delegate_failure_capture import maybe_capture_from_delegate_result

        maybe_capture_from_delegate_result(
            role=role,
            task=task,
            context=context,
            success=success,
            issues=issues,
            parent_session_key=parent_session_key,
            child_session_key=child_session_key,
            task_id=task_id,
            project=project,
            dev_engine=dev_engine,
        )

    safe_best_effort(_run, label="delegate_report.failure_capture", default=None)

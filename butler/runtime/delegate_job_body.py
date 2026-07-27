"""Delegate job execution body - split from delegate_job.py for maintainability."""

from __future__ import annotations

import logging
from typing import Any

from butler.core.best_effort import safe_best_effort
from butler.execution_context import use_execution_context
from butler.report import AgentReport, attach_delegate_task_times, cache_report
from butler.report.acceptance_card import attach_delegate_acceptance_meta
from butler.runtime.delegate_job_finalize import (
    attach_delegate_diff_summary,
    record_delegate_observability,
    record_delegate_turn_done,
)
from butler.runtime.delegate_registry import (
    register_delegate_loop,
    unregister_delegate_loop,
)
from butler.runtime.task_store import complete_task
from butler.session.lifecycle import sync_turn_memory
from butler.tools.builtin_impl import _delegate_role_label as _canonical_delegate_role_label
from butler.tools.delegate_impl import finalize_delegate_success
from butler.tools.delegate_phases import peek_dev_engine_summary
from butler.tools.registry import (
    _extract_changes_from_messages,
    _extract_issues_from_messages,
    _run_subagent_stop_hooks,
)

logger = logging.getLogger(__name__)


def _prepare_delegate_context(job) -> Any:
    """Prepare execution context for delegate job."""
    if job.bridge is not None:
        safe_best_effort(
            lambda: __import__(
                "butler.gateway.outbound_bridge", fromlist=["set_current_bridge"]
            ).set_current_bridge(job.bridge),
            label="delegate_job.set_bridge",
            default=None,
        )

    run_cbs = safe_best_effort(
        lambda: __import__(
            "butler.ops.langfuse_tracer", fromlist=["delegate_run_callbacks"]
        ).delegate_run_callbacks(
            parent_session_key=job.session_key,
            child_session_key=job.child_session_key or job.session_key,
            role=job.role,
            task=job.task,
            task_id=job.task_id,
        ),
        label="delegate_job.langfuse_callbacks",
        default=None,
    )
    return run_cbs


def _execute_delegate_loop(job, run_cbs) -> Any:
    """Execute the delegate agent loop."""
    with use_execution_context(job.orch, session_key=job.child_session_key or job.session_key):
        register_delegate_loop(job.session_key, job.agent)
        try:
            if run_cbs is not None:
                return job.agent.run(job.user_msg, run_callbacks=run_cbs)
            else:
                return job.agent.run(job.user_msg)
        finally:
            unregister_delegate_loop(job.session_key, job.agent)


def _sync_delegate_memory(job, result) -> None:
    """Sync delegate result to turn memory."""
    sync_turn_memory(
        job.orch,
        job.raw_user_msg,
        (result.final_response or "") if result else "",
        interrupted=result.status.value == "interrupted" if result else False,
        status=result.status if result else None,
        session_id=job.session_key,
    )


def _finalize_delegate_success_with_issues(job, result):
    """Finalize delegate success and extract issues."""
    changes = _extract_changes_from_messages(result.messages) if result else []
    issues = _extract_issues_from_messages(result.messages) if result else []
    project = safe_best_effort(
        lambda: job.orch.project_manager.get_current() if job.orch else None,
        label="delegate_job.resolve_project",
        default=None,
    )

    dev_engine = None
    success = False

    if result:
        dev_engine = peek_dev_engine_summary(
            job.child_session_key or job.session_key or "_default",
            job.role,
        )
        success, issues = finalize_delegate_success(
            result,
            changes,
            issues,
            category=str(job.category_meta.get("category") or ""),
            category_meta=job.category_meta,
            project=project,
            role=job.role,
            dev_engine=dev_engine,
            task=job.task or "",
            messages=list(getattr(result, "messages", None) or []),
            summary=str(getattr(result, "final_response", "") or "").strip(),
        )
    else:
        success = False

    return success, issues, changes, project, dev_engine


def _build_delegate_headline(job, success, issues) -> str:
    """Build delegate headline based on success status and issues."""
    role_label = _delegate_role_label(job.role)
    if success:
        return f"{role_label}已完成任务"
    elif any("DEV_VERIFY_GATE" in str(i) for i in issues):
        return f"{role_label}已完成编辑但未通过验证"
    elif any("DELETE_VERIFY_GATE" in str(i) for i in issues):
        return f"{role_label}未能完成任务"
    else:
        return f"{role_label}未能完成任务"


def _build_delegate_summary(result) -> str:
    """Build delegate summary text."""
    summary_text = (result.final_response or "").strip() if result else ""
    if not summary_text:
        return (
            "DELEGATE_EMPTY_RESPONSE: 子代理未返回有效摘要。"
            "请缩小任务范围或换 category/role 后重试。"
        )
    return summary_text


def _create_delegate_report(job, success, result, changes, issues, dev_engine, project):
    """Create and populate delegate report."""
    role_label = _delegate_role_label(job.role)

    summary_text = _build_delegate_summary(result)
    if not summary_text:
        success = False

    headline = _build_delegate_headline(job, success, issues)

    record_delegate_turn_done(job, success=success, result=result)

    task_preview = (job.task or "").strip()[:200]
    report = AgentReport(
        headline=headline,
        summary=summary_text or "(无输出)",
        changes=changes,
        issues=issues,
        success=success,
        task_preview=task_preview,
        task_id=job.task_id,
        child_session_key=job.child_session_key,
        iterations=getattr(result, "iterations", 0) if result else 0,
        tool_calls=getattr(result, "tool_calls_made", 0) if result else 0,
        tokens_used=getattr(result, "total_tokens", 0) if result else 0,
        elapsed_seconds=getattr(result, "elapsed_seconds", 0.0) if result else 0.0,
    )
    attach_delegate_acceptance_meta(
        report,
        role=job.role,
        project=project,
        dev_engine=dev_engine,
        task=job.task or "",
        task_preview=task_preview,
        category_meta=job.category_meta,
    )
    complete_task(
        job.task_id,
        success=success,
        report_headline=report.headline,
        summary=report.summary,
    )
    attach_delegate_task_times(report, job.task_id)
    cache_report(report, session_key=job.session_key)

    return report, success, issues, dev_engine


def _notify_delegate_completion(job, report, success, issues, dev_engine):
    """Notify about delegate completion."""
    from butler.runtime.delegate_job import push_delegate_completion

    _run_subagent_stop_hooks(
        role=job.role,
        agent_id=job.task_id or f"delegate-{job.role}",
        success=success,
        task_id=job.task_id,
        session_key=job.session_key,
        summary_preview=report.summary,
    )
    attach_delegate_diff_summary(report, job)
    push_delegate_completion(
        report,
        bridge=job.bridge,
        push_target=job.push_target,
        use_async_push=job.use_async_push,
    )
    record_delegate_observability(
        job,
        success=success,
        issues=issues,
        dev_engine=dev_engine,
    )
    logger.info(
        "Background delegate finished task_id=%s success=%s",
        job.task_id,
        success,
    )


def run_delegate_job_body(job) -> None:
    """Main body for delegate job execution."""
    run_cbs = _prepare_delegate_context(job)
    result = _execute_delegate_loop(job, run_cbs)
    _sync_delegate_memory(job, result)

    success, issues, changes, project, dev_engine = _finalize_delegate_success_with_issues(
        job, result
    )
    report, success, issues, dev_engine = _create_delegate_report(
        job, success, result, changes, issues, dev_engine, project
    )
    _notify_delegate_completion(job, report, success, issues, dev_engine)


def _delegate_role_label(role: str) -> str:
    return str(_canonical_delegate_role_label(role))


__all__ = [
    "run_delegate_job_body",
]

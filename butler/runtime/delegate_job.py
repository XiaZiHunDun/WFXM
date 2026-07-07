"""Background and foreground delegate execution."""

from __future__ import annotations

import json
import logging
from typing import Any

from butler.core.best_effort import safe_best_effort
from butler.execution_context import use_execution_context
from butler.gateway.completion_notify import (
    build_report_push_text,
    delegate_completion_enabled,
    deliver_completion_push,
)
from butler.report import AgentReport, attach_delegate_task_times, cache_report
from butler.report.acceptance_card import attach_delegate_acceptance_meta
from butler.runtime.delegate_async_result import build_async_delegate_tool_result
from butler.runtime.delegate_job_finalize import (
    attach_delegate_diff_summary,
    record_delegate_observability,
    record_delegate_turn_done,
    run_delegate_job_inner_guarded,
)
from butler.runtime.delegate_progress import delegate_progress_heartbeat
from butler.runtime.delegate_registry import (
    register_delegate_loop,
    unregister_delegate_loop,
)
from butler.runtime.notify import push_runtime_message
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
from butler.runtime.delegate_job_types import DelegateJob, DelegatePushTarget

logger = logging.getLogger(__name__)


def push_delegate_completion(
    report: Any,
    *,
    bridge: Any | None = None,
    push_target: DelegatePushTarget | None = None,
    use_async_push: bool = False,
) -> bool:
    """WeChat notify when a delegate finishes (sync or background)."""
    if not delegate_completion_enabled():
        return False

    prefix = "📋 委派已完成（后台）" if use_async_push else "📋 委派阶段完成"
    text = build_report_push_text(report, prefix=prefix)

    if push_target is not None and push_target.loop is not None:
        import asyncio

        async def _send() -> None:
            await deliver_completion_push(
                push_target.adapter,
                push_target.chat_id,
                text,
                kind="delegate",
            )

        def _schedule() -> bool:
            asyncio.run_coroutine_threadsafe(_send(), push_target.loop)
            return True

        if safe_best_effort(
            _schedule,
            label="delegate_job.async_push_schedule",
            default=False,
        ):
            return True

    if bridge is not None and not use_async_push:

        def _notify() -> bool:
            bridge.notify_delegate_finished(report)
            return True

        if safe_best_effort(_notify, label="delegate_job.bridge_notify", default=False):
            return True

    def _runtime_push() -> bool:
        return bool(push_runtime_message("[Butler] 委派完成", text))

    return bool(
        safe_best_effort(_runtime_push, label="delegate_job.runtime_push", default=False)
    )


def run_delegate_job(job: DelegateJob) -> None:
    """Execute delegate agent loop (intended for background thread)."""
    with delegate_progress_heartbeat(job):
        _run_delegate_job_inner(job)


def _run_delegate_job_inner(job: DelegateJob) -> None:
    run_delegate_job_inner_guarded(job, _run_delegate_job_body)


def _run_delegate_job_body(job: DelegateJob) -> None:
    result = None
    success = False
    dev_engine = None
    if job.bridge is not None:
        safe_best_effort(
            lambda: __import__(
                "butler.gateway.outbound_bridge", fromlist=["set_current_bridge"]
            ).set_current_bridge(job.bridge),
            label="delegate_job.set_bridge",
            default=None,
        )
    with use_execution_context(job.orch, session_key=job.child_session_key or job.session_key):
        register_delegate_loop(job.session_key, job.agent)
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
        try:
            if run_cbs is not None:
                result = job.agent.run(job.user_msg, run_callbacks=run_cbs)
            else:
                result = job.agent.run(job.user_msg)
        finally:
            unregister_delegate_loop(job.session_key, job.agent)

    sync_turn_memory(
        job.orch,
        job.raw_user_msg,
        (result.final_response or "") if result else "",
        interrupted=result.status.value == "interrupted" if result else False,
        status=result.status if result else None,
        session_id=job.session_key,
    )

    changes = _extract_changes_from_messages(result.messages) if result else []
    issues = _extract_issues_from_messages(result.messages) if result else []
    project = safe_best_effort(
        lambda: job.orch.project_manager.get_current() if job.orch else None,
        label="delegate_job.resolve_project",
        default=None,
    )
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
        )
    else:
        success = False
    role_label = _delegate_role_label(job.role)
    if success:
        headline = f"{role_label}已完成任务"
    elif any("DEV_VERIFY_GATE" in str(i) for i in issues):
        headline = f"{role_label}已完成编辑但未通过验证"
    else:
        headline = f"{role_label}未能完成任务"
    summary_text = (result.final_response or "").strip() if result else ""
    if not summary_text:
        summary_text = (
            "DELEGATE_EMPTY_RESPONSE: 子代理未返回有效摘要。"
            "请缩小任务范围或换 category/role 后重试。"
        )
        success = False
        headline = f"{role_label}返回空结果"

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


def _delegate_role_label(role: str) -> str:
    return str(_canonical_delegate_role_label(role))

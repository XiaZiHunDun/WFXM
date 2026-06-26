"""Delegate phase 6 — report, payload, and observability (ENG-2)."""

from __future__ import annotations

import json
import logging
from typing import Any

from butler.dev_engine.delegate_finalize import (
    attach_dev_engine_summary,
    peek_dev_engine_summary,
)
from butler.tools.delegate_run_state import DelegateRunState

logger = logging.getLogger(__name__)


def sync_turn_memory_for_result(state: DelegateRunState, result: Any) -> None:
    """Sync turn memory using the pre-handoff context (6a)."""
    from butler.session.lifecycle import sync_turn_memory

    sync_turn_memory(
        state.orch,
        state.memory_sync_user_msg,
        result.final_response or "",
        interrupted=result.status.value == "interrupted",
        status=result.status,
        session_id=state.session_key,
    )


def build_delegate_report(
    state: DelegateRunState,
    result: Any,
    changes: list,
    issues: list,
):
    """Build the ``AgentReport`` (6b + 6d), including empty-response fallback."""
    from butler.report import AgentReport
    from butler.tools.delegate_impl import (
        _delegate_role_label,
        finalize_delegate_success,
    )

    de_summary = peek_dev_engine_summary(
        state.child_session_key or state.session_key or "_default",
        state.role,
    )
    success, issues = finalize_delegate_success(
        result,
        changes,
        issues,
        category=str(state.category_meta.get("category") or state.category or ""),
        category_meta=state.category_meta,
        project=state.project,
        role=state.role,
        dev_engine=de_summary,
        task=state.task or "",
    )
    role_label = _delegate_role_label(state.role)
    if success:
        headline = f"{role_label}已完成任务"
    elif any("DEV_VERIFY_GATE" in str(i) for i in issues):
        headline = f"{role_label}已完成编辑但未通过验证"
    else:
        headline = f"{role_label}未能完成任务"
    task_preview = (state.task or "").strip()[:200]
    summary_text = (result.final_response or "").strip()
    if not summary_text:
        summary_text = (
            "DELEGATE_EMPTY_RESPONSE: 子代理未返回有效摘要。"
            "请缩小任务范围或换 category/role 后重试。"
        )
        success = False
        headline = f"{role_label}返回空结果"
    report = AgentReport(
        headline=headline,
        summary=summary_text or "(无输出)",
        changes=changes,
        issues=issues,
        success=success,
        task_preview=task_preview,
        task_id=state.task_id,
        child_session_key=state.child_session_key,
        iterations=result.iterations,
        tool_calls=result.tool_calls_made,
        tokens_used=result.total_tokens,
        elapsed_seconds=result.elapsed_seconds,
    )
    from butler.report.acceptance_card import attach_delegate_acceptance_meta

    attach_delegate_acceptance_meta(
        report,
        role=state.role,
        project=state.project,
        dev_engine=de_summary,
        task=state.task or "",
        task_preview=task_preview,
        category_meta=state.category_meta,
    )
    return report


def record_delegate_turn_done(state: DelegateRunState, success: bool, result: Any) -> None:
    """Emit the ``delegate_turn_done`` session-transcript event (6c)."""
    if not state.child_session_key:
        return
    from butler.core.session_transcript import record_generic_event

    record_generic_event(
        state.child_session_key,
        "delegate_turn_done",
        {
            "task_id": state.task_id,
            "success": success,
            "iterations": getattr(result, "iterations", 0),
        },
    )


def finalize_delegate_task(state: DelegateRunState, report: Any) -> None:
    """Cache report, complete task, stop hooks, bridge notify (6e)."""
    from butler.report import cache_report, attach_delegate_task_times
    from butler.runtime.task_store import complete_task
    from butler.tools.delegate_impl import _run_subagent_stop_hooks

    complete_task(
        state.task_id,
        success=report.success,
        report_headline=report.headline,
        summary=report.summary,
    )
    attach_delegate_task_times(report, state.task_id)
    cache_report(report, session_key=state.session_key)
    try:
        from butler.ops.owner_pmf_metrics import record_acceptance_card

        record_acceptance_card(report, session_key=state.session_key)
    except Exception:
        pass
    _run_subagent_stop_hooks(
        role=state.role,
        agent_id=state.task_id or f"delegate-{state.role}",
        success=report.success,
        task_id=state.task_id,
        session_key=state.session_key,
        summary_preview=report.summary,
    )
    if state.bridge is not None:
        state.bridge.notify_delegate_finished(report)


def build_result_payload(state: DelegateRunState, report: Any, result: Any) -> dict[str, Any]:
    """Build the tool-result JSON payload (6f)."""
    payload: dict[str, Any] = {
        "success": report.success,
        "headline": report.headline,
        "summary": report.summary[:2000],
        "task_id": state.task_id,
        "child_session_key": state.child_session_key,
        "iterations": report.iterations,
        "tool_calls": report.tool_calls,
        "tokens": report.tokens_used,
    }
    if state.category_meta.get("category"):
        payload["category"] = state.category_meta["category"]
    if not (result.final_response or "").strip():
        payload["code"] = "DELEGATE_EMPTY_RESPONSE"
    diag = getattr(result, "diagnostics", None) or {}
    tool_names = diag.get("tools_used")
    if isinstance(tool_names, list) and tool_names:
        payload["tools_used"] = [str(n) for n in tool_names if n]
    attach_dev_engine_summary(state, payload)
    return payload


def finalize_delegate_observability(
    state: DelegateRunState,
    report: Any,
    issues: list[str],
    payload: dict[str, Any],
) -> None:
    """Close delegate LangFuse span and capture production failures."""
    dev_engine = payload.get("dev_engine") if isinstance(payload.get("dev_engine"), dict) else None
    try:
        from butler.ops.langfuse_tracer import finish_delegate_trace

        finish_delegate_trace(
            state.child_session_key or state.session_key,
            success=report.success,
            metadata={
                "task_id": state.task_id,
                "role": state.role,
                "issues": issues[:3],
                "dev_engine": dev_engine or {},
            },
        )
    except Exception as exc:  # noqa: BLE001 — best-effort tracing
        logger.debug("delegate LangFuse finalize skipped: %s", exc)

    trace_id = ""
    try:
        from butler.ops.langfuse_tracer import get_current_trace, get_delegate_trace

        delegate_ctx = get_delegate_trace(state.child_session_key or state.session_key)
        if delegate_ctx is not None:
            trace_id = delegate_ctx.trace_id
        parent = get_current_trace(state.session_key)
        if not trace_id and parent is not None:
            trace_id = parent.trace_id
    except Exception as exc:  # noqa: BLE001 — best-effort trace lookup
        logger.debug("delegate trace id lookup skipped: %s", exc)

    try:
        from butler.ops.delegate_judge import maybe_judge_and_push

        maybe_judge_and_push(
            success=report.success,
            issues=issues,
            dev_engine=dev_engine,
            task=state.task,
            summary=getattr(report, "summary", ""),
            trace_id=trace_id,
        )
    except Exception as exc:  # noqa: BLE001 — best-effort judge
        logger.debug("delegate judge skipped: %s", exc)

    try:
        from butler.ops.delegate_failure_capture import maybe_capture_from_delegate_result

        project_name = ""
        if state.project is not None:
            project_name = str(getattr(state.project, "name", "") or "")
        maybe_capture_from_delegate_result(
            role=state.role,
            task=state.task,
            context=state.original_context or state.context,
            success=report.success,
            issues=issues,
            parent_session_key=state.session_key,
            child_session_key=state.child_session_key or state.session_key,
            task_id=state.task_id,
            project=project_name,
            dev_engine=dev_engine,
        )
    except Exception as exc:  # noqa: BLE001 — best-effort capture
        logger.debug("delegate failure capture skipped: %s", exc)


def format_delegate_result(state: DelegateRunState, result: Any) -> str:
    """Phase 6: memory sync, report, cache, complete_task, hooks, payload."""
    from butler.tools.delegate_impl import (
        _extract_changes_from_messages,
        _extract_issues_from_messages,
    )

    sync_turn_memory_for_result(state, result)
    changes = _extract_changes_from_messages(result.messages)
    issues = _extract_issues_from_messages(result.messages)
    report = build_delegate_report(state, result, changes, issues)
    record_delegate_turn_done(state, report.success, result)
    finalize_delegate_task(state, report)
    payload = build_result_payload(state, report, result)
    finalize_delegate_observability(state, report, issues, payload)
    return json.dumps(payload, ensure_ascii=False)


__all__ = [
    "build_delegate_report",
    "build_result_payload",
    "finalize_delegate_observability",
    "finalize_delegate_task",
    "format_delegate_result",
    "peek_dev_engine_summary",
    "record_delegate_turn_done",
    "sync_turn_memory_for_result",
]

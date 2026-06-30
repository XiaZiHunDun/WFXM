"""Delegate task tool implementation and helpers."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _orchestrator_for_tool(*, channel: str):
    from butler.execution_context import get_current_orchestrator

    orch = get_current_orchestrator()
    if orch is not None:
        return orch

    from butler.orchestrator import ButlerOrchestrator

    return ButlerOrchestrator(user_id="owner", channel=channel)


def _project_agent_raw_message(*, task: str, context: str = "") -> str:
    user_msg = task
    if context:
        user_msg = f"## 上下文\n{context}\n\n## 任务\n{task}"
    return user_msg


def _inject_project_agent_skills(orch: Any, user_msg: str) -> str:
    inject = getattr(orch, "inject_skill_context", None)
    if callable(inject):
        return inject(user_msg)
    return user_msg


def _delegate_role_label(role: str) -> str:
    key = str(role or "").strip().lower()
    labels = {
        "content_agent": "内容代理",
        "content": "内容代理",
        "dev_agent": "开发代理",
        "dev": "开发代理",
        "review_agent": "审核代理",
        "review": "审核代理",
        "butler": "管家",
    }
    return labels.get(key, str(role or "代理"))


def _extract_issues_from_messages(messages: list) -> list[str]:
    import json as _json

    issues: list[str] = []
    seen: set[str] = set()
    for msg in messages or []:
        if msg.get("role") != "tool":
            continue
        content = str(msg.get("content") or "")
        err = ""
        try:
            payload = _json.loads(content)
            if isinstance(payload, dict):
                err = str(payload.get("error") or "").strip()
        except _json.JSONDecodeError:
            pass
        if not err and '"error"' in content.lower():
            err = content[:400].strip()
        if err and err not in seen:
            seen.add(err)
            issues.append(err[:500])
    return issues[:5]


def _delegate_task_succeeded(result: Any, changes: list, issues: list) -> bool:
    if result.status.value != "completed":
        return False
    if issues and not changes:
        return False
    return True


def finalize_delegate_success(
    result: Any,
    changes: list,
    issues: list,
    *,
    category: str = "",
    category_meta: dict[str, Any] | None = None,
    project: Any = None,
    role: str = "",
    dev_engine: dict[str, Any] | None = None,
    task: str = "",
    task_preview: str = "",
) -> tuple[bool, list[str]]:
    """Base delegate success + category gates (B9 pytest) + dev auto-verify."""
    base = _delegate_task_succeeded(result, changes, issues)
    out_issues = list(issues or [])
    try:
        from butler.dev_engine.b9_delegate_gate import (
            apply_b9_pytest_success_gate,
            apply_coding_strict_pilot_gate,
            apply_dev_auto_verify_success_gate,
            apply_dev_review_strict_gate,
        )

        ok, out_issues = apply_b9_pytest_success_gate(
            category=category,
            category_meta=category_meta,
            project=project,
            base_success=base,
            issues=out_issues,
        )
        ok, out_issues = apply_dev_auto_verify_success_gate(
            role=role,
            base_success=ok,
            issues=out_issues,
            dev_engine=dev_engine,
            task=task,
            task_preview=task_preview or (task or "")[:200],
            changes=changes,
            category_meta=category_meta,
        )
        ok, out_issues = apply_coding_strict_pilot_gate(
            category=category,
            category_meta=category_meta,
            role=role,
            base_success=ok,
            issues=out_issues,
            dev_engine=dev_engine,
        )
        return apply_dev_review_strict_gate(
            category=category,
            category_meta=category_meta,
            role=role,
            base_success=ok,
            issues=out_issues,
            dev_engine=dev_engine,
        )
    except Exception as exc:
        logger.debug("delegate success gate skipped: %s", exc)
        return base, out_issues


def _extract_changes_from_messages(messages: list) -> list:
    import json as _json

    from butler.report import Change

    changes: list[Change] = []
    for msg in messages or []:
        if msg.get("role") != "tool":
            continue
        content = str(msg.get("content") or "")
        lowered = content.lower()
        if '"success": true' not in lowered and '"success":true' not in lowered:
            continue
        path = ""
        action = "modified"
        try:
            payload = _json.loads(content)
            if isinstance(payload, dict):
                path = str(payload.get("path") or "").strip()
                raw_action = str(payload.get("action") or "").strip().lower()
                if raw_action in {"created", "modified", "deleted"}:
                    action = raw_action
                elif payload.get("replacements"):
                    action = "modified"
                elif payload.get("bytes") is not None and not payload.get("replacements"):
                    action = "created"
        except _json.JSONDecodeError:
            pass
        if not path and "write_file" in lowered:
            action = "created"
        if not path and "delete_file" in lowered:
            action = "deleted"
        if not path:
            path = "(文件变更)"
        changes.append(
            Change(
                file=path,
                action=action if action in {"created", "modified", "deleted"} else "modified",
                description="",
            )
        )
    return changes[:10]


def _safe_dispatch(name: str, args: dict, depth: int) -> str:
    from butler.delegate.policy import DELEGATE_BLOCKED_TOOLS
    if name in DELEGATE_BLOCKED_TOOLS:
        return json.dumps({"error": f"Tool '{name}' is blocked in delegated agents"})
    if name == "delegate_task":
        args = {**args, "depth": depth}
    from butler.tools.registry import dispatch_tool as _dispatch
    result = _dispatch(name, args)
    try:
        from butler.memory.corrective_recall import (
            build_corrective_recall_block,
            should_trigger_corrective,
        )

        if should_trigger_corrective(name, result):
            task_hint = str(args.get("task") or args.get("query") or args.get("path") or "")
            block = build_corrective_recall_block(
                task=task_hint,
                tool_name=name,
                error_excerpt=result[:400],
            )
            if block:
                result = f"{result}\n\n{block}"
    except Exception as exc:
        logger.debug("corrective recall injection skipped: %s", exc)
    return result


def _run_subagent_stop_hooks(
    *,
    role: str,
    agent_id: str,
    success: bool,
    task_id: str = "",
    session_key: str = "",
    summary_preview: str = "",
) -> None:
    try:
        from butler.hooks.runner import run_subagent_stop_hooks

        run_subagent_stop_hooks(
            agent_type=role,
            agent_id=agent_id,
            success=success,
            task_id=task_id,
            session_key=session_key,
            summary_preview=summary_preview,
        )
    except Exception as exc:
        logger.debug("SubagentStop hooks skipped: %s", exc)


def _finalize_delegate_failure(
    *,
    role: str,
    task: str,
    exc: Exception,
    task_id: str = "",
    session_key: str = "",
    project: str = "",
) -> str:
    from butler.report import AgentReport, cache_report
    from butler.runtime.task_store import complete_task

    role_label = _delegate_role_label(role)
    headline = f"{role_label}委派失败"
    summary = str(exc)[:2000]
    if task_id:
        complete_task(
            task_id,
            success=False,
            report_headline=headline,
            summary=summary,
        )
    report = AgentReport(
        headline=headline,
        summary=summary,
        success=False,
        task_preview=(task or "")[:200],
        task_id=task_id,
        issues=[summary[:500]],
    )
    cache_report(report, session_key=session_key or "default")
    _run_subagent_stop_hooks(
        role=role,
        agent_id=task_id or f"delegate-{role}",
        success=False,
        task_id=task_id,
        session_key=session_key,
        summary_preview=summary,
    )
    try:
        from butler.ops.delegate_failure_capture import maybe_capture_from_delegate_result

        maybe_capture_from_delegate_result(
            role=role,
            task=task,
            success=False,
            issues=[summary[:500]],
            parent_session_key=session_key,
            child_session_key=session_key,
            task_id=task_id,
            project=project,
            dev_engine=None,
        )
    except Exception as cap_exc:
        logger.debug("delegate failure capture on exception skipped: %s", cap_exc)
    try:
        # R1-10: bridge lookup routed through the execution_context seam
        # so tools → gateway stays a one-way dependency.
        from butler.execution_context import get_current_turn_bridge

        br = get_current_turn_bridge()
        if br is not None:
            br.notify_delegate_finished(report)
    except Exception as exc:
        logger.debug("delegate finished notification skipped: %s", exc)
    payload: dict[str, Any] = {
        "success": False,
        "error": f"Delegation failed: {exc}",
        "headline": headline,
    }
    if task_id:
        payload["task_id"] = task_id
    return json.dumps(payload, ensure_ascii=False)


def _tool_delegate_task(
    role: str,
    task: str,
    context: str = "",
    category: str = "",
    depth: int = 0,
    **_,
) -> str:
    """Delegate to a project-level agent through Butler's orchestrator.

    R1-5 split: the original 408-line body now delegates to six phase
    helpers in :mod:`butler.tools.delegate_phases`. The host keeps the
    try/except boundary so :func:`_finalize_delegate_failure` still owns
    the single failure-finalize path (no behavior change).

    R1-10: bridge lookup routed through the ``butler.execution_context``
    seam so tools → gateway stays a one-way dependency.
    """
    from butler.execution_context import get_current_turn_bridge
    from butler.tools.delegate_phases import (
        DelegateRunState,
        _build_user_message,
        _format_delegate_result,
        _prepare_delegate_task,
        _record_delegate_state,
        _resolve_subagent,
        _run_subagent_loop,
    )

    state = DelegateRunState(
        role=role,
        task=task,
        context=context,
        category=category,
        depth=depth,
        original_context=context,
        bridge=get_current_turn_bridge(),
    )
    try:
        # Phase 1: enrich (role/task/context/category) + depth check
        _prepare_delegate_task(state)
        if state.early_return:
            return state.early_return

        # Phase 2: orchestrator + project + tools + agent
        _resolve_subagent(state)

        # Phase 3: assemble user message
        _build_user_message(state)

        # Phase 4: prefetch + semaphore + task record + hooks + transcript
        _record_delegate_state(state)
        if state.early_return:
            return state.early_return

        # Phase 5: dispatch (async vs sync) + run + release
        async_payload = _run_subagent_loop(state)
        if async_payload is not None:
            return async_payload
        result = state.sync_result

        # Phase 6: build report + payload
        return _format_delegate_result(state, result)

    except Exception as exc:
        logger.error("Delegation to %s failed: %s", role, exc)
        project_name = ""
        if state.project is not None:
            project_name = str(getattr(state.project, "name", "") or "")
        return _finalize_delegate_failure(
            role=state.role,
            task=state.task,
            exc=exc,
            task_id=state.task_id,
            session_key=state.session_key,
            project=project_name,
        )

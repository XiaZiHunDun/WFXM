"""Delegate task tool implementation and helpers."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, cast
from butler.core.best_effort import safe_best_effort
from butler.delegate.policy import DELEGATE_BLOCKED_TOOLS
from butler.execution_context import get_current_turn_bridge
from butler.report import AgentReport, Change, cache_report
from butler.runtime.task_store import complete_task
from butler.tools.delegate_orchestrator import _orchestrator_for_tool


def _project_agent_raw_message(*, task: str, context: str = "") -> str:
    user_msg = task
    if context:
        user_msg = f"## 上下文\n{context}\n\n## 任务\n{task}"
    return user_msg


def _inject_project_agent_skills(orch: Any, user_msg: str) -> str:
    inject = getattr(orch, "inject_skill_context", None)
    if callable(inject):
        return str(inject(user_msg))
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


def _extract_issues_from_messages(messages: list[Any]) -> list[str]:
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


def _delegate_task_succeeded(result: Any, changes: list[Any], issues: list[str]) -> bool:
    if result.status.value != "completed":
        return False
    if issues and not changes:
        return False
    return True


def finalize_delegate_success(
    result: Any,
    changes: list[Any],
    issues: list[str],
    *,
    category: str = "",
    category_meta: dict[str, Any] | None = None,
    project: Any = None,
    role: str = "",
    dev_engine: dict[str, Any] | None = None,
    task: str = "",
    task_preview: str = "",
    messages: list[Any] | None = None,
    summary: str = "",
) -> tuple[bool, list[str]]:
    """Base delegate success + category gates (B9 pytest) + dev auto-verify."""
    base = _delegate_task_succeeded(result, changes, issues)
    out_issues = list(issues or [])
    summary_text = summary or str(getattr(result, "final_response", "") or "").strip()
    msg_list = messages if messages is not None else list(getattr(result, "messages", None) or [])

    return cast(
        tuple[bool, list[str]],
        apply_delegate_success_gates(
            base=base,
            issues=out_issues,
            category=category,
            category_meta=category_meta,
            project=project,
            role=role,
            dev_engine=dev_engine,
            task=task,
            task_preview=task_preview,
            changes=changes,
            messages=msg_list,
            summary=summary_text,
        ),
    )


def _extract_changes_from_messages(messages: list[Any]) -> list[Any]:
    import json as _json


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


def _safe_dispatch(name: str, args: dict[str, Any], depth: int) -> str:
    from butler.tools.registry import dispatch_tool as _dispatch

    if name in DELEGATE_BLOCKED_TOOLS:
        return json.dumps({"error": f"Tool '{name}' is blocked in delegated agents"})
    if name == "delegate_task":
        args = {**args, "depth": depth}
    result = _dispatch(name, args)

    return str(inject_corrective_recall_safe(name, args, result))


def _run_subagent_stop_hooks(
    *,
    role: str,
    agent_id: str,
    success: bool,
    task_id: str = "",
    session_key: str = "",
    summary_preview: str = "",
) -> None:

    run_subagent_stop_hooks_safe(
        role=role,
        agent_id=agent_id,
        success=success,
        task_id=task_id,
        session_key=session_key,
        summary_preview=summary_preview,
    )


def _finalize_delegate_failure(
    *,
    role: str,
    task: str,
    exc: Exception,
    task_id: str = "",
    session_key: str = "",
    project: str = "",
) -> str:

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

    capture_delegate_failure_safe(
        role=role,
        task=task,
        summary=summary,
        session_key=session_key,
        task_id=task_id,
        project=project,
    )

    notify_delegate_finished_safe(get_current_turn_bridge(), report)
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
    **_: Any,
) -> str:
    """Delegate to a project-level agent through Butler's orchestrator.

    R1-5 split: the original 408-line body now delegates to six phase
    helpers in :mod:`butler.tools.delegate_phases`. The host keeps the
    try/except boundary so :func:`_finalize_delegate_failure` still owns
    the single failure-finalize path (no behavior change).

    R1-10: bridge lookup routed through the ``butler.execution_context``
    seam so tools → gateway stays a one-way dependency.
    """

    return str(
        run_delegate_task_loud(
            role=role,
            task=task,
            context=context,
            category=category,
            depth=depth,
            finalize_failure=_finalize_delegate_failure,
        )
    )


def apply_delegate_success_gates(
    *,
    base: bool,
    issues: list[str],
    category: str,
    category_meta: dict[str, Any] | None,
    project: Any,
    role: str,
    dev_engine: dict[str, Any] | None,
    task: str,
    task_preview: str,
    changes: list[Any],
    messages: list[Any] | None = None,
    summary: str = "",
) -> tuple[bool, list[str]]:
    def _run() -> tuple[bool, list[str]]:
        from butler.dev_engine.b9_delegate_gate import (
            apply_b9_pytest_success_gate,
            apply_coding_strict_pilot_gate,
            apply_dev_auto_verify_success_gate,
            apply_dev_review_strict_gate,
        )
        from butler.tools.delegate_delete_gate import apply_delegate_delete_verify_gate

        out_issues = list(issues or [])
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
        ok, out_issues = apply_delegate_delete_verify_gate(
            base_success=ok,
            issues=out_issues,
            task=task,
            task_preview=task_preview or (task or "")[:200],
            changes=changes,
            project=project,
            messages=messages,
            summary=summary,
        )
        final = apply_dev_review_strict_gate(
            category=category,
            category_meta=category_meta,
            role=role,
            base_success=ok,
            issues=out_issues,
            dev_engine=dev_engine,
        )
        if isinstance(final, tuple) and len(final) == 2:
            f_ok, f_issues = final
            return bool(f_ok), list(f_issues) if isinstance(f_issues, list) else out_issues
        return ok, out_issues

    result = safe_best_effort(
        _run,
        label="delegate_impl.success_gates",
        default=(base, list(issues or [])),
    )
    if isinstance(result, tuple) and len(result) == 2:
        ok, out = result
        return bool(ok), list(out) if isinstance(out, list) else list(issues or [])
    return base, list(issues or [])


def inject_corrective_recall_safe(name: str, args: dict[str, Any], result: str) -> str:
    def _run() -> str:
        from butler.memory.corrective_recall import (
            build_corrective_recall_block,
            should_trigger_corrective,
        )

        if not should_trigger_corrective(name, result):
            return result
        task_hint = str(args.get("task") or args.get("query") or args.get("path") or "")
        block = build_corrective_recall_block(
            task=task_hint,
            tool_name=name,
            error_excerpt=result[:400],
        )
        if block:
            return f"{result}\n\n{block}"
        return result

    out = safe_best_effort(
        _run,
        label="delegate_impl.corrective_recall",
        default=result,
    )
    return out if isinstance(out, str) else result


def run_subagent_stop_hooks_safe(
    *,
    role: str,
    agent_id: str,
    success: bool,
    task_id: str = "",
    session_key: str = "",
    summary_preview: str = "",
) -> None:
    def _run() -> None:
        from butler.hooks.runner import run_subagent_stop_hooks

        run_subagent_stop_hooks(
            agent_type=role,
            agent_id=agent_id,
            success=success,
            task_id=task_id,
            session_key=session_key,
            summary_preview=summary_preview,
        )

    safe_best_effort(_run, label="delegate_impl.subagent_stop_hooks", default=None)


def capture_delegate_failure_safe(
    *,
    role: str,
    task: str,
    summary: str,
    session_key: str,
    task_id: str,
    project: str,
) -> None:
    def _run() -> None:
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

    safe_best_effort(_run, label="delegate_impl.failure_capture", default=None)


def notify_delegate_finished_safe(bridge: Any, report: Any) -> None:
    def _run() -> None:
        if bridge is not None:
            bridge.notify_delegate_finished(report)

    safe_best_effort(_run, label="delegate_impl.finished_notify", default=None)


def run_delegate_task_loud(
    *,
    role: str,
    task: str,
    context: str,
    category: str,
    depth: int,
    finalize_failure: Any,
) -> str:
    """Run delegate phases; single fail-closed boundary for tool entry."""
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
        _prepare_delegate_task(state)
        if state.early_return:
            return str(state.early_return)
        _resolve_subagent(state)
        _build_user_message(state)
        _record_delegate_state(state)
        if state.early_return:
            return str(state.early_return)
        async_payload = _run_subagent_loop(state)
        if async_payload is not None:
            return str(async_payload)
        return str(_format_delegate_result(state, state.sync_result))
    except (RuntimeError, ValueError, AttributeError, KeyError, TypeError, OSError, IndexError) as exc:
        logger.error("Delegation to %s failed: %s", role, exc)
        project_name = ""
        if state.project is not None:
            project_name = str(getattr(state.project, "name", "") or "")
        return str(
            finalize_failure(
                role=state.role,
                task=state.task,
                exc=exc,
                task_id=state.task_id,
                session_key=state.session_key,
                project=project_name,
            )
        )

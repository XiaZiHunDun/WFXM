"""Delegate task tool implementation and helpers."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, cast
from butler.delegate.policy import DELEGATE_BLOCKED_TOOLS
from butler.execution_context import get_current_orchestrator, get_current_turn_bridge
from butler.report import AgentReport, Change, cache_report
from butler.runtime.task_store import complete_task
from butler.tools.delegate_impl_ops import (
    apply_delegate_success_gates,
    capture_delegate_failure_safe,
    inject_corrective_recall_safe,
    notify_delegate_finished_safe,
    run_delegate_task_loud,
    run_subagent_stop_hooks_safe,
)


def _orchestrator_for_tool(*, channel: str) -> Any:

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
) -> tuple[bool, list[str]]:
    """Base delegate success + category gates (B9 pytest) + dev auto-verify."""
    base = _delegate_task_succeeded(result, changes, issues)
    out_issues = list(issues or [])

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

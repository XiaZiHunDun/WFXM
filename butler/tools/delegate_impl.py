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
        from butler.gateway.outbound_bridge import get_gateway_bridge_optional

        br = get_gateway_bridge_optional()
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
    """Delegate to a project-level agent through Butler's orchestrator."""
    task_id = ""
    session_key = ""
    category_meta: dict[str, Any] = {}
    original_context = context
    try:
        from butler.delegate.policy import MAX_DELEGATE_DEPTH
        from butler.gateway.outbound_bridge import get_gateway_bridge_optional

        if not str(category or "").strip():
            try:
                from butler.core.intent_keywords import category_from_intent

                inferred = category_from_intent(task)
                if inferred:
                    category = inferred
            except Exception as exc:
                logger.debug("intent category inference skipped: %s", exc)

        if str(category or "").strip():
            from butler.delegate.category_resolver import apply_category_to_delegate

            role, task, context, category_meta = apply_category_to_delegate(
                category=str(category).strip(),
                role=role,
                task=task,
                context=context,
            )

        from butler.core.handoff import merge_handoff_into_context, render_handoff_block

        cat_name = str(category or category_meta.get("category") or "").strip().lower()
        needs_handoff = (
            cat_name.startswith("nexus")
            or cat_name == "ui-build"
            or "## Handoff" not in str(context or "")
        )
        if needs_handoff:
            from butler.core.handoff import default_visual_acceptance

            if cat_name == "ui-build":
                acceptance = default_visual_acceptance()
                evidence_required = ["read_file DESIGN.md", "read_file 改动文件"]
            else:
                acceptance = [
                    "任务描述中的目标已达成",
                    "关键改动有 read_file 或测试证据",
                ]
                evidence_required = ["read_file 或 pytest"]
            handoff = render_handoff_block(
                from_role="butler",
                to_role=str(role or "dev"),
                task=task,
                acceptance=acceptance,
                evidence_required=evidence_required,
            )
            context = merge_handoff_into_context(context, handoff)

        try:
            from butler.agent_profiles import DELEGATE_VERIFY_CHECKLIST

            if DELEGATE_VERIFY_CHECKLIST.strip():
                context = (context or "").rstrip() + "\n\n" + DELEGATE_VERIFY_CHECKLIST.strip()
        except Exception as exc:
            logger.debug("delegate verify checklist skipped: %s", exc)

        bridge = get_gateway_bridge_optional()
        if bridge is not None:
            bridge.notify_delegate_start(role, preview=task[:80])

        if depth >= MAX_DELEGATE_DEPTH:
            return json.dumps({"error": f"Maximum delegation depth ({MAX_DELEGATE_DEPTH}) exceeded"})

        orch = _orchestrator_for_tool(channel="cli")
        from butler.tools.project_tools import get_tool_definitions_for_project

        project = orch.project_manager.get_current()
        if project is not None:
            try:
                from butler.agents_md import merge_agent_md_into_context

                context = merge_agent_md_into_context(
                    Path(project.workspace),
                    role,
                    context,
                )
            except Exception as exc:
                logger.debug("agents.md merge skipped: %s", exc)
        tools = get_tool_definitions_for_project(project, role=role)

        from butler.delegate.subagent_permissions import filter_tools_for_subagent

        workspace = Path(project.workspace) if project is not None else None
        delegated_tools = filter_tools_for_subagent(
            tools,
            workspace=workspace,
            role=role,
        )
        allow_only = category_meta.get("allow_tools")
        deny_extra = category_meta.get("deny_tools")
        if isinstance(allow_only, list) and allow_only:
            allow_set = {str(t).strip() for t in allow_only if str(t).strip()}
            delegated_tools = [
                t
                for t in delegated_tools
                if str((t.get("function") or {}).get("name") or "") in allow_set
            ]
        if isinstance(deny_extra, list):
            deny_set = {str(t).strip() for t in deny_extra if str(t).strip()}
            delegated_tools = [
                t
                for t in delegated_tools
                if str((t.get("function") or {}).get("name") or "") not in deny_set
            ]

        from butler.core.delegate_context import child_callbacks, get_parent_callbacks

        parent_cb = get_parent_callbacks()
        agent = orch.create_project_agent_loop(
            role=role,
            tools=delegated_tools,
            tool_dispatcher=lambda name, args: _safe_dispatch(name, args, depth + 1),
            callbacks=child_callbacks(parent_cb),
        )
        from butler.core.cache_safe_delegate import (
            apply_cache_safe_system_prompt,
            delegate_diagnostics,
        )
        from butler.core.delegate_context import get_parent_system_prompt

        from butler.core.delegate_context import get_parent_messages

        parent_sys = get_parent_system_prompt()
        parent_msgs = get_parent_messages()
        if parent_sys:
            merged = apply_cache_safe_system_prompt(
                parent_sys,
                agent.system_prompt,
                tools=delegated_tools,
                messages=parent_msgs,
            )
            agent.system_prompt = merged
            agent.diagnostics.update(
                delegate_diagnostics(
                    parent_sys,
                    merged,
                    tools=delegated_tools,
                    messages=parent_msgs,
                )
            )
        from butler.delegate.policy import resolve_delegate_max_iterations

        agent.config.max_iterations = resolve_delegate_max_iterations(category_meta)
        try:
            from butler.delegate.policy import delegate_one_tool_per_iteration

            if delegate_one_tool_per_iteration():
                agent.config.enable_parallel_tools = False
                agent.diagnostics["delegate_one_tool_per_iteration"] = True
        except Exception as exc:
            logger.debug("delegate one-tool-per-iteration policy skipped: %s", exc)

        agent.reset()

        raw_user_msg = _project_agent_raw_message(task=task, context=context)
        memory_sync_user_msg = _project_agent_raw_message(
            task=task,
            context=original_context,
        )
        user_msg = _inject_project_agent_skills(orch, raw_user_msg)

        from butler.session.lifecycle import attach_turn_memory_prefetch, sync_turn_memory
        from butler.execution_context import get_current_session_key, use_execution_context
        from butler.runtime.task_store import complete_task, create_task

        attach_turn_memory_prefetch(agent, orch, raw_user_msg, role=role)

        session_key = str(get_current_session_key() or "").strip()
        from butler.core.delegate_semaphore import try_acquire_delegate_slot

        if not try_acquire_delegate_slot(session_key):
            from butler.core.delegate_semaphore import max_concurrent_delegates

            return json.dumps({
                "error": (
                    f"本会话并发委派已达上限 ({max_concurrent_delegates()})，"
                    "请等待进行中的任务完成。"
                ),
                "code": "DELEGATE_CONCURRENCY",
            })
        project_name = ""
        if project is not None:
            project_name = str(getattr(project, "name", "") or "")
        from butler.runtime.task_store import delegate_group_id

        group_id = delegate_group_id(session_key)
        task_record = create_task(
            session_key=session_key,
            role=role,
            task_preview=task,
            project=project_name,
            group_id=group_id,
        )
        task_id = str(task_record.get("task_id") or "")
        child_session_key = str(task_record.get("child_session_key") or "")

        try:
            from butler.hooks.runner import run_subagent_start_hooks

            subagent_ctx = run_subagent_start_hooks(
                agent_type=role,
                agent_id=task_id or f"delegate-{role}",
                task_preview=task,
                task_id=task_id,
                session_key=session_key,
            )
            if subagent_ctx:
                user_msg = "\n\n".join(subagent_ctx) + "\n\n" + user_msg
        except Exception as exc:
            logger.debug("SubagentStart hooks skipped: %s", exc)

        from butler.core.session_transcript import record_generic_event

        if child_session_key:
            record_generic_event(
                session_key,
                "delegate_started",
                {
                    "task_id": task_id,
                    "child_session_key": child_session_key,
                    "role": role,
                },
            )
            record_generic_event(
                child_session_key,
                "delegate_turn_start",
                {"task_id": task_id, "parent_session_key": session_key, "role": role},
            )

        from butler.runtime.async_delegate import (
            schedule_background_delegate,
            should_delegate_async,
            push_target_from_bridge,
        )
        from butler.runtime.delegate_job import (
            DelegateJob,
            build_async_delegate_tool_result,
        )

        if should_delegate_async(
            bridge=bridge,
            depth=depth,
            category_meta=category_meta,
        ):
            push_tgt = push_target_from_bridge(bridge) if bridge is not None else None
            schedule_background_delegate(
                DelegateJob(
                    agent=agent,
                    orch=orch,
                    user_msg=user_msg,
                    raw_user_msg=raw_user_msg,
                    role=role,
                    task=task,
                    session_key=session_key,
                    child_session_key=child_session_key,
                    task_id=task_id,
                    category_meta=category_meta,
                    bridge=bridge,
                    push_target=push_tgt,
                )
            )
            return build_async_delegate_tool_result(
                task_id=task_id,
                child_session_key=child_session_key,
                role=role,
                task_preview=task,
                category=str(category_meta.get("category") or category or ""),
            )

        try:
            with use_execution_context(orch, session_key=child_session_key or session_key):
                try:
                    from butler.runtime.delegate_registry import (
                        register_delegate_loop,
                        unregister_delegate_loop,
                    )

                    register_delegate_loop(session_key, agent)
                    result = agent.run(user_msg)
                finally:
                    try:
                        from butler.runtime.delegate_registry import unregister_delegate_loop

                        unregister_delegate_loop(session_key, agent)
                    except Exception as exc:
                        logger.debug("delegate loop unregister skipped: %s", exc)
        finally:
            from butler.core.delegate_semaphore import release_delegate_slot

            release_delegate_slot(session_key)

        sync_turn_memory(
            orch,
            memory_sync_user_msg,
            result.final_response or "",
            interrupted=result.status.value == "interrupted",
            status=result.status,
            session_id=session_key,
        )

        from butler.report import AgentReport

        changes = _extract_changes_from_messages(result.messages)
        issues = _extract_issues_from_messages(result.messages)
        success = _delegate_task_succeeded(result, changes, issues)
        role_label = _delegate_role_label(role)
        headline = (
            f"{role_label}已完成任务"
            if success
            else f"{role_label}未能完成任务"
        )
        task_preview = (task or "").strip()[:200]
        summary_text = (result.final_response or "").strip()
        if not summary_text:
            summary_text = (
                "DELEGATE_EMPTY_RESPONSE: 子代理未返回有效摘要。"
                "请缩小任务范围或换 category/role 后重试。"
            )
            success = False
            headline = f"{role_label}返回空结果"

        if child_session_key:
            record_generic_event(
                child_session_key,
                "delegate_turn_done",
                {
                    "task_id": task_id,
                    "success": success,
                    "iterations": getattr(result, "iterations", 0),
                },
            )

        report = AgentReport(
            headline=headline,
            summary=summary_text or "(无输出)",
            changes=changes,
            issues=issues,
            success=success,
            task_preview=task_preview,
            task_id=task_id,
            child_session_key=child_session_key,
            iterations=result.iterations,
            tool_calls=result.tool_calls_made,
            tokens_used=result.total_tokens,
            elapsed_seconds=result.elapsed_seconds,
        )

        from butler.report import cache_report
        cache_report(report, session_key=session_key)
        complete_task(
            task_id,
            success=success,
            report_headline=report.headline,
            summary=report.summary,
        )
        _run_subagent_stop_hooks(
            role=role,
            agent_id=task_id or f"delegate-{role}",
            success=success,
            task_id=task_id,
            session_key=session_key,
            summary_preview=report.summary,
        )
        if bridge is not None:
            bridge.notify_delegate_finished(report)

        payload: dict[str, Any] = {
            "success": report.success,
            "headline": report.headline,
            "summary": report.summary[:2000],
            "task_id": task_id,
            "child_session_key": child_session_key,
            "iterations": report.iterations,
            "tool_calls": report.tool_calls,
            "tokens": report.tokens_used,
        }
        if category_meta.get("category"):
            payload["category"] = category_meta["category"]
        if not (result.final_response or "").strip():
            payload["code"] = "DELEGATE_EMPTY_RESPONSE"
        return json.dumps(payload, ensure_ascii=False)

    except Exception as exc:
        logger.error("Delegation to %s failed: %s", role, exc)
        return _finalize_delegate_failure(
            role=role,
            task=task,
            exc=exc,
            task_id=task_id,
            session_key=session_key,
        )

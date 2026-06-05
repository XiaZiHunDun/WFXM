"""Phase helpers extracted from ``_tool_delegate_task`` (R1-5 split).

Original ``butler/tools/delegate_impl.py::_tool_delegate_task`` was a
408-line god function. The host now delegates to six phase helpers:

- :func:`_prepare_delegate_task`  — category / handoff / verify / depth check
- :func:`_resolve_subagent`       — orchestrator / tools / agent construction
- :func:`_build_user_message`     — raw + skills injection
- :func:`_record_delegate_state`  — prefetch / semaphore / task record / hooks
- :func:`_run_subagent_loop`      — async-vs-sync / register / run / release
- :func:`_format_delegate_result` — sync memory / report / payload

A :class:`DelegateRunState` carrier threads state between phases. Early
returns (depth / concurrency) set ``state.early_return`` so the host's
``try/except`` keeps one failure-finalize path.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class DelegateRunState:
    """Mutable carrier passed through phase helpers of ``_tool_delegate_task``.

    All fields start empty; each phase populates the fields it owns.
    Using a small carrier avoids passing 10+ parameters between helpers
    and keeps the host function readable.
    """

    # --- input -----------------------------------------------------------
    role: str = ""
    task: str = ""
    context: str = ""
    category: str = ""
    depth: int = 0
    original_context: str = ""

    # --- resolved during phases ------------------------------------------
    category_meta: dict[str, Any] = field(default_factory=dict)
    bridge: Any = None
    orch: Any = None
    project: Any = None
    tools: list = field(default_factory=list)
    delegated_tools: list = field(default_factory=list)
    agent: Any = None
    user_msg: str = ""
    raw_user_msg: str = ""
    memory_sync_user_msg: str = ""
    session_key: str = ""
    task_id: str = ""
    child_session_key: str = ""

    # --- control flow ----------------------------------------------------
    # When non-empty, the host should return this JSON string immediately
    # (depth exceeded, concurrency exceeded, async dispatch result).
    early_return: str = ""
    # Sync-run result lives here when ``_run_subagent_loop`` returns None.
    sync_result: Any = None


def _prepare_delegate_task(state: DelegateRunState) -> None:
    """Phase 1: enrich (role, task, context, category) and check depth.

    Populates ``state.category_meta``, ``state.context``, and sets
    ``state.early_return`` when ``depth >= MAX_DELEGATE_DEPTH``.
    Order preserved from the original host: category inference → category
    resolver → handoff block → verify checklist → bridge notify → depth check.
    """
    # 1a. infer category from intent
    if not str(state.category or "").strip():
        try:
            from butler.core.intent_keywords import category_from_intent

            inferred = category_from_intent(state.task)
            if inferred:
                state.category = inferred
        except Exception as exc:  # noqa: BLE001 — best-effort inference
            logger.debug("intent category inference skipped: %s", exc)

    # 1b. apply category resolver (rewrites role/task/context)
    if str(state.category or "").strip():
        from butler.delegate.category_resolver import apply_category_to_delegate

        new_role, new_task, new_context, category_meta = apply_category_to_delegate(
            category=str(state.category).strip(),
            role=state.role,
            task=state.task,
            context=state.context,
        )
        state.role = new_role
        state.task = new_task
        state.context = new_context
        state.category_meta = category_meta

    # 1c. handoff block (nexus / ui-build / first time)
    from butler.core.handoff import merge_handoff_into_context, render_handoff_block

    cat_name = str(state.category or state.category_meta.get("category") or "").strip().lower()
    needs_handoff = (
        cat_name.startswith("nexus")
        or cat_name == "ui-build"
        or "## Handoff" not in str(state.context or "")
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
            to_role=str(state.role or "dev"),
            task=state.task,
            acceptance=acceptance,
            evidence_required=evidence_required,
        )
        state.context = merge_handoff_into_context(state.context, handoff)

    # 1d. verify checklist (best-effort)
    try:
        from butler.agent_profiles import DELEGATE_VERIFY_CHECKLIST

        if DELEGATE_VERIFY_CHECKLIST.strip():
            state.context = (state.context or "").rstrip() + "\n\n" + DELEGATE_VERIFY_CHECKLIST.strip()
    except Exception as exc:  # noqa: BLE001 — best-effort injection
        logger.debug("delegate verify checklist skipped: %s", exc)

    # 1e. bridge notify (start)
    if state.bridge is not None:
        state.bridge.notify_delegate_start(state.role, preview=state.task[:80])

    # 1f. depth check (early return)
    from butler.delegate.policy import MAX_DELEGATE_DEPTH

    if state.depth >= MAX_DELEGATE_DEPTH:
        state.early_return = json.dumps(
            {"error": f"Maximum delegation depth ({MAX_DELEGATE_DEPTH}) exceeded"}
        )


def _resolve_subagent(state: DelegateRunState) -> None:
    """Phase 2: build the project agent loop with cache-safe prompt.

    Populates ``state.orch``, ``state.project``, ``state.tools``,
    ``state.delegated_tools``, ``state.agent``.
    """
    from butler.tools.delegate_impl import _orchestrator_for_tool, _safe_dispatch

    # 2a. orchestrator
    state.orch = _orchestrator_for_tool(channel="cli")

    # 2b. project + agents.md context merge
    state.project = state.orch.project_manager.get_current()
    if state.project is not None:
        try:
            from butler.agents_md import merge_agent_md_into_context

            state.context = merge_agent_md_into_context(
                Path(state.project.workspace),
                state.role,
                state.context,
            )
        except Exception as exc:  # noqa: BLE001 — best-effort merge
            logger.debug("agents.md merge skipped: %s", exc)

    # 2c. tools + subagent filter + allow/deny
    from butler.tools.project_tools import get_tool_definitions_for_project

    state.tools = get_tool_definitions_for_project(state.project, role=state.role)

    from butler.delegate.subagent_permissions import filter_tools_for_subagent

    workspace = Path(state.project.workspace) if state.project is not None else None
    state.delegated_tools = filter_tools_for_subagent(
        state.tools,
        workspace=workspace,
        role=state.role,
    )
    allow_only = state.category_meta.get("allow_tools")
    deny_extra = state.category_meta.get("deny_tools")
    if isinstance(allow_only, list) and allow_only:
        allow_set = {str(t).strip() for t in allow_only if str(t).strip()}
        state.delegated_tools = [
            t
            for t in state.delegated_tools
            if str((t.get("function") or {}).get("name") or "") in allow_set
        ]
    if isinstance(deny_extra, list):
        deny_set = {str(t).strip() for t in deny_extra if str(t).strip()}
        state.delegated_tools = [
            t
            for t in state.delegated_tools
            if str((t.get("function") or {}).get("name") or "") not in deny_set
        ]

    # 2d. create agent loop with safe dispatch + child callbacks
    from butler.core.delegate_context import child_callbacks, get_parent_callbacks

    parent_cb = get_parent_callbacks()
    state.agent = state.orch.create_project_agent_loop(
        role=state.role,
        tools=state.delegated_tools,
        tool_dispatcher=lambda name, args: _safe_dispatch(name, args, state.depth + 1),
        callbacks=child_callbacks(parent_cb),
    )

    # 2e. cache-safe system prompt + diagnostics
    from butler.core.cache_safe_delegate import (
        apply_cache_safe_system_prompt,
        delegate_diagnostics,
    )
    from butler.core.delegate_context import (
        get_parent_messages,
        get_parent_system_prompt,
    )

    parent_sys = get_parent_system_prompt()
    parent_msgs = get_parent_messages()
    if parent_sys:
        merged = apply_cache_safe_system_prompt(
            parent_sys,
            state.agent.system_prompt,
            tools=state.delegated_tools,
            messages=parent_msgs,
        )
        state.agent.system_prompt = merged
        state.agent.diagnostics.update(
            delegate_diagnostics(
                parent_sys,
                merged,
                tools=state.delegated_tools,
                messages=parent_msgs,
            )
        )

    # 2f. max iterations + one-tool-per-iter policy
    from butler.delegate.policy import resolve_delegate_max_iterations

    state.agent.config.max_iterations = resolve_delegate_max_iterations(state.category_meta)
    try:
        from butler.delegate.policy import delegate_one_tool_per_iteration

        if delegate_one_tool_per_iteration():
            state.agent.config.enable_parallel_tools = False
            state.agent.diagnostics["delegate_one_tool_per_iteration"] = True
    except Exception as exc:  # noqa: BLE001 — best-effort policy
        logger.debug("delegate one-tool-per-iteration policy skipped: %s", exc)

    state.agent.reset()


def _build_user_message(state: DelegateRunState) -> None:
    """Phase 3: assemble the user message (raw + skills + memory sync)."""
    from butler.tools.delegate_impl import (
        _inject_project_agent_skills,
        _project_agent_raw_message,
    )

    state.raw_user_msg = _project_agent_raw_message(task=state.task, context=state.context)
    state.memory_sync_user_msg = _project_agent_raw_message(
        task=state.task,
        context=state.original_context,
    )
    state.user_msg = _inject_project_agent_skills(state.orch, state.raw_user_msg)


def _record_delegate_state(state: DelegateRunState) -> None:
    """Phase 4: prefetch, semaphore, task record, hooks, transcript.

    Populates ``state.session_key``, ``state.task_id``,
    ``state.child_session_key``. Sets ``state.early_return`` if the
    concurrency semaphore is exhausted for the current session.
    """
    # 4a. memory prefetch
    from butler.session.lifecycle import attach_turn_memory_prefetch

    attach_turn_memory_prefetch(state.agent, state.orch, state.raw_user_msg, role=state.role)

    # 4b. session key
    from butler.execution_context import get_current_session_key

    state.session_key = str(get_current_session_key() or "").strip()

    # 4c. concurrency semaphore
    from butler.core.delegate_semaphore import (
        max_concurrent_delegates,
        try_acquire_delegate_slot,
    )

    if not try_acquire_delegate_slot(state.session_key):
        state.early_return = json.dumps({
            "error": (
                f"本会话并发委派已达上限 ({max_concurrent_delegates()}),"
                "请等待进行中的任务完成。"
            ),
            "code": "DELEGATE_CONCURRENCY",
        })
        return

    # 4d. task record
    from butler.runtime.task_store import create_task, delegate_group_id

    project_name = ""
    if state.project is not None:
        project_name = str(getattr(state.project, "name", "") or "")
    group_id = delegate_group_id(state.session_key)
    task_record = create_task(
        session_key=state.session_key,
        role=state.role,
        task_preview=state.task,
        project=project_name,
        group_id=group_id,
    )
    state.task_id = str(task_record.get("task_id") or "")
    state.child_session_key = str(task_record.get("child_session_key") or "")

    # 4e. subagent start hooks
    try:
        from butler.hooks.runner import run_subagent_start_hooks

        subagent_ctx = run_subagent_start_hooks(
            agent_type=state.role,
            agent_id=state.task_id or f"delegate-{state.role}",
            task_preview=state.task,
            task_id=state.task_id,
            session_key=state.session_key,
        )
        if subagent_ctx:
            state.user_msg = "\n\n".join(subagent_ctx) + "\n\n" + state.user_msg
    except Exception as exc:  # noqa: BLE001 — best-effort hooks
        logger.debug("SubagentStart hooks skipped: %s", exc)

    # 4f. session transcript events
    if state.child_session_key:
        from butler.core.session_transcript import record_generic_event

        record_generic_event(
            state.session_key,
            "delegate_started",
            {
                "task_id": state.task_id,
                "child_session_key": state.child_session_key,
                "role": state.role,
            },
        )
        record_generic_event(
            state.child_session_key,
            "delegate_turn_start",
            {
                "task_id": state.task_id,
                "parent_session_key": state.session_key,
                "role": state.role,
            },
        )


def _run_subagent_loop(state: DelegateRunState) -> str | None:
    """Phase 5: dispatch (async vs sync), register, run, release semaphore.

    Returns a JSON string for the async-dispatched path (caller returns
    this verbatim). For the sync path, returns ``None`` and the caller
    consumes ``state.sync_result`` then continues to :func:`_format_delegate_result`.
    """
    # 5a. async dispatch?
    from butler.runtime.async_delegate import (
        push_target_from_bridge,
        schedule_background_delegate,
        should_delegate_async,
    )

    if should_delegate_async(
        bridge=state.bridge,
        depth=state.depth,
        category_meta=state.category_meta,
    ):
        from butler.runtime.delegate_job import (
            DelegateJob,
            build_async_delegate_tool_result,
        )

        push_tgt = push_target_from_bridge(state.bridge) if state.bridge is not None else None
        schedule_background_delegate(
            DelegateJob(
                agent=state.agent,
                orch=state.orch,
                user_msg=state.user_msg,
                raw_user_msg=state.raw_user_msg,
                role=state.role,
                task=state.task,
                session_key=state.session_key,
                child_session_key=state.child_session_key,
                task_id=state.task_id,
                category_meta=state.category_meta,
                bridge=state.bridge,
                push_target=push_tgt,
            )
        )
        return build_async_delegate_tool_result(
            task_id=state.task_id,
            child_session_key=state.child_session_key,
            role=state.role,
            task_preview=state.task,
            category=str(state.category_meta.get("category") or state.category or ""),
        )

    # 5b. sync path: register, run, unregister, release
    from butler.execution_context import use_execution_context
    from butler.core.delegate_semaphore import release_delegate_slot

    try:
        with use_execution_context(
            state.orch, session_key=state.child_session_key or state.session_key
        ):
            try:
                from butler.runtime.delegate_registry import (
                    register_delegate_loop,
                    unregister_delegate_loop,
                )

                register_delegate_loop(state.session_key, state.agent)
                state.sync_result = state.agent.run(state.user_msg)
            finally:
                try:
                    from butler.runtime.delegate_registry import unregister_delegate_loop

                    unregister_delegate_loop(state.session_key, state.agent)
                except Exception as exc:  # noqa: BLE001 — best-effort unregister
                    logger.debug("delegate loop unregister skipped: %s", exc)
    finally:
        release_delegate_slot(state.session_key)

    return None


def _format_delegate_result(state: DelegateRunState, result: Any) -> str:
    """Phase 6: memory sync, report, cache, complete_task, hooks, payload."""
    from butler.core.session_transcript import record_generic_event
    from butler.report import AgentReport, cache_report
    from butler.runtime.task_store import complete_task
    from butler.session.lifecycle import sync_turn_memory
    from butler.tools.delegate_impl import (
        _delegate_role_label,
        _delegate_task_succeeded,
        _extract_changes_from_messages,
        _extract_issues_from_messages,
        _run_subagent_stop_hooks,
    )

    # 6a. memory sync (uses original_context, not the handoff-injected one)
    sync_turn_memory(
        state.orch,
        state.memory_sync_user_msg,
        result.final_response or "",
        interrupted=result.status.value == "interrupted",
        status=result.status,
        session_id=state.session_key,
    )

    # 6b. extract changes/issues + success
    changes = _extract_changes_from_messages(result.messages)
    issues = _extract_issues_from_messages(result.messages)
    success = _delegate_task_succeeded(result, changes, issues)
    role_label = _delegate_role_label(state.role)
    headline = (
        f"{role_label}已完成任务"
        if success
        else f"{role_label}未能完成任务"
    )
    task_preview = (state.task or "").strip()[:200]
    summary_text = (result.final_response or "").strip()
    if not summary_text:
        summary_text = (
            "DELEGATE_EMPTY_RESPONSE: 子代理未返回有效摘要。"
            "请缩小任务范围或换 category/role 后重试。"
        )
        success = False
        headline = f"{role_label}返回空结果"

    # 6c. session transcript
    if state.child_session_key:
        record_generic_event(
            state.child_session_key,
            "delegate_turn_done",
            {
                "task_id": state.task_id,
                "success": success,
                "iterations": getattr(result, "iterations", 0),
            },
        )

    # 6d. build AgentReport
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

    # 6e. cache + complete + stop hooks + bridge notify
    cache_report(report, session_key=state.session_key)
    complete_task(
        state.task_id,
        success=success,
        report_headline=report.headline,
        summary=report.summary,
    )
    _run_subagent_stop_hooks(
        role=state.role,
        agent_id=state.task_id or f"delegate-{state.role}",
        success=success,
        task_id=state.task_id,
        session_key=state.session_key,
        summary_preview=report.summary,
    )
    if state.bridge is not None:
        state.bridge.notify_delegate_finished(report)

    # 6f. payload
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
    return json.dumps(payload, ensure_ascii=False)

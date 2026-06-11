"""Phase helpers extracted from ``_tool_delegate_task`` (R1-5 split).

Original ``butler/tools/delegate_impl.py::_tool_delegate_task`` was a
408-line god function. The host now delegates to six thin phase
orchestrators (each < 50 lines, contract-enforced by
``tests/test_delegate_impl_split.py::TestPhaseFunctionsUnder50Lines``):

- :func:`_prepare_delegate_task`  — category / handoff / verify / depth check
- :func:`_resolve_subagent`       — orchestrator / tools / agent construction
- :func:`_build_user_message`     — raw + skills injection
- :func:`_record_delegate_state`  — prefetch / semaphore / task record / hooks
- :func:`_run_subagent_loop`      — async-vs-sync / register / run / release
- :func:`_format_delegate_result` — sync memory / report / payload

Each phase delegates to focused private helpers (``_infer_*`` /
``_apply_*`` / ``_build_*`` / ``_record_*`` / ``_finalize_*``) that
keep the phase function a small orchestrator. R1-5.2 (code-quality
reviewer feedback) further split 4/6 phases that breached the 50-line
ceiling after R1-5.

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
    tools: list[dict[str, Any]] = field(default_factory=list)
    delegated_tools: list[dict[str, Any]] = field(default_factory=list)
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


def _infer_delegate_category(task: str) -> str:
    """Best-effort category inference from task intent (1a)."""
    try:
        from butler.core.intent_keywords import category_from_intent

        return str(category_from_intent(task) or "")
    except Exception as exc:  # noqa: BLE001 — best-effort inference
        logger.debug("intent category inference skipped: %s", exc)
        return ""


def _apply_category_resolver(state: DelegateRunState) -> None:
    """Apply category resolver — rewrites role/task/context (1b)."""
    if not str(state.category or "").strip():
        return
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


def _build_handoff_block_text(cat_name: str, role: str, task: str) -> str:
    """Render the handoff markdown for a category (1c, pure)."""
    from butler.core.handoff import default_visual_acceptance, render_handoff_block

    if cat_name == "ui-build":
        acceptance = default_visual_acceptance()
        evidence_required = ["read_file DESIGN.md", "read_file 改动文件"]
    else:
        acceptance = [
            "任务描述中的目标已达成",
            "关键改动有 read_file 或测试证据",
        ]
        evidence_required = ["read_file 或 pytest"]
    return render_handoff_block(
        from_role="butler",
        to_role=str(role or "dev"),
        task=task,
        acceptance=acceptance,
        evidence_required=evidence_required,
    )


def _inject_handoff_block(state: DelegateRunState) -> None:
    """Inject handoff markdown for nexus / ui-build / first-time (1c)."""
    from butler.core.handoff import merge_handoff_into_context

    cat_name = str(
        state.category or state.category_meta.get("category") or ""
    ).strip().lower()
    needs_handoff = (
        cat_name.startswith("nexus")
        or cat_name == "ui-build"
        or "## Handoff" not in str(state.context or "")
    )
    if not needs_handoff:
        return
    handoff = _build_handoff_block_text(cat_name, state.role, state.task)
    state.context = merge_handoff_into_context(state.context, handoff)


def _inject_verify_checklist(state: DelegateRunState) -> None:
    """Append the delegate verify checklist to context (1d, best-effort)."""
    try:
        from butler.agent_profiles import DELEGATE_VERIFY_CHECKLIST

        text = DELEGATE_VERIFY_CHECKLIST.strip()
        if text:
            state.context = (state.context or "").rstrip() + "\n\n" + text
    except Exception as exc:  # noqa: BLE001 — best-effort injection
        logger.debug("delegate verify checklist skipped: %s", exc)


def _check_delegate_depth(state: DelegateRunState) -> None:
    """Set ``early_return`` when ``depth >= MAX_DELEGATE_DEPTH`` (1f)."""
    from butler.delegate.policy import MAX_DELEGATE_DEPTH

    if state.depth >= MAX_DELEGATE_DEPTH:
        state.early_return = json.dumps(
            {"error": f"Maximum delegation depth ({MAX_DELEGATE_DEPTH}) exceeded"}
        )


def _prepare_delegate_task(state: DelegateRunState) -> None:
    """Phase 1: enrich (role, task, context, category) and check depth.

    Populates ``state.category_meta``, ``state.context``, and sets
    ``state.early_return`` when ``depth >= MAX_DELEGATE_DEPTH``.
    Order preserved from the original host: category inference → category
    resolver → handoff block → verify checklist → bridge notify → depth check.
    """
    if not str(state.category or "").strip():
        state.category = _infer_delegate_category(state.task)
    _apply_category_resolver(state)
    _inject_handoff_block(state)
    _inject_verify_checklist(state)
    if state.bridge is not None:
        state.bridge.notify_delegate_start(state.role, preview=state.task[:80])
    _check_delegate_depth(state)


def _attach_agents_md_context(state: DelegateRunState) -> None:
    """Merge ``AGENTS.md`` into context for the current project (2b)."""
    if state.project is None:
        return
    try:
        from butler.agents_md import merge_agent_md_into_context

        state.context = merge_agent_md_into_context(
            Path(state.project.workspace),
            state.role,
            state.context,
        )
    except Exception as exc:  # noqa: BLE001 — best-effort merge
        logger.debug("agents.md merge skipped: %s", exc)


def _build_subagent_tools(state: DelegateRunState) -> None:
    """Populate ``state.tools`` and ``state.delegated_tools`` (2c base)."""
    from butler.delegate.subagent_permissions import filter_tools_for_subagent
    from butler.tools.project_tools import get_tool_definitions_for_project

    state.tools = get_tool_definitions_for_project(state.project, role=state.role)
    workspace = Path(state.project.workspace) if state.project is not None else None
    state.delegated_tools = filter_tools_for_subagent(
        state.tools,
        workspace=workspace,
        role=state.role,
    )


def _apply_subagent_tool_filters(state: DelegateRunState) -> None:
    """Apply allow/deny allowlists from category_meta (2c allow/deny)."""
    allow_only = state.category_meta.get("allow_tools")
    deny_extra = state.category_meta.get("deny_tools")

    def _tool_name(t: dict[str, Any]) -> str:
        return str((t.get("function") or {}).get("name") or "")

    if isinstance(allow_only, list) and allow_only:
        allow_set = {str(t).strip() for t in allow_only if str(t).strip()}
        state.delegated_tools = [
            t for t in state.delegated_tools if _tool_name(t) in allow_set
        ]
    if isinstance(deny_extra, list):
        deny_set = {str(t).strip() for t in deny_extra if str(t).strip()}
        state.delegated_tools = [
            t for t in state.delegated_tools if _tool_name(t) not in deny_set
        ]


def _create_project_agent_loop(state: DelegateRunState) -> None:
    """Create the child agent loop with safe dispatch + child callbacks (2d)."""
    from butler.core.delegate_context import child_callbacks, get_parent_callbacks
    from butler.tools.delegate_impl import _safe_dispatch

    parent_cb = get_parent_callbacks()
    state.agent = state.orch.create_project_agent_loop(
        role=state.role,
        tools=state.delegated_tools,
        tool_dispatcher=lambda name, args: _safe_dispatch(name, args, state.depth + 1),
        callbacks=child_callbacks(parent_cb),
    )


def _apply_cache_safe_prompt(state: DelegateRunState) -> None:
    """Merge parent system prompt + record cache diagnostics (2e)."""
    from butler.core.cache_safe_delegate import (
        apply_cache_safe_system_prompt,
        delegate_diagnostics,
    )
    from butler.core.delegate_context import (
        get_parent_messages,
        get_parent_system_prompt,
    )

    parent_sys = get_parent_system_prompt()
    if not parent_sys:
        return
    parent_msgs = get_parent_messages()
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


def _configure_subagent_policy(state: DelegateRunState) -> None:
    """Apply max-iterations + one-tool-per-iter policy (2f)."""
    from butler.delegate.policy import resolve_delegate_max_iterations

    state.agent.config.max_iterations = resolve_delegate_max_iterations(state.category_meta)
    try:
        from butler.delegate.policy import delegate_one_tool_per_iteration

        if delegate_one_tool_per_iteration():
            state.agent.config.enable_parallel_tools = False
            state.agent.diagnostics["delegate_one_tool_per_iteration"] = True
    except Exception as exc:  # noqa: BLE001 — best-effort policy
        logger.debug("delegate one-tool-per-iteration policy skipped: %s", exc)


def _inject_dev_engine_prompt(state: DelegateRunState) -> None:
    """Append dev engine system prompt when role=dev and engine enabled (2g)."""
    norm = state.role.replace("_agent", "").strip().lower()
    if norm != "dev":
        return
    try:
        from butler.agent_profiles import get_dev_agent_prompt

        enhanced = get_dev_agent_prompt()
        if enhanced and len(enhanced) > len(state.agent.system_prompt):
            state.agent.system_prompt = enhanced
    except Exception as exc:  # noqa: BLE001 — best-effort injection
        logger.debug("dev engine prompt injection skipped: %s", exc)


def _resolve_subagent(state: DelegateRunState) -> None:
    """Phase 2: build the project agent loop with cache-safe prompt.

    Populates ``state.orch``, ``state.project``, ``state.tools``,
    ``state.delegated_tools``, ``state.agent``.
    """
    from butler.tools.delegate_impl import _orchestrator_for_tool

    state.orch = _orchestrator_for_tool(channel="cli")
    state.project = state.orch.project_manager.get_current()
    _attach_agents_md_context(state)
    _build_subagent_tools(state)
    _apply_subagent_tool_filters(state)
    _create_project_agent_loop(state)
    _inject_dev_engine_prompt(state)
    _apply_cache_safe_prompt(state)
    _configure_subagent_policy(state)
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


def _acquire_delegate_slot(state: DelegateRunState) -> bool:
    """Acquire a concurrency slot for the current session (4c).

    Returns ``True`` on success. On failure, sets ``state.early_return``
    to a JSON error payload and returns ``False``.
    """
    from butler.core.delegate_semaphore import (
        max_concurrent_delegates,
        try_acquire_delegate_slot,
    )

    if try_acquire_delegate_slot(state.session_key):
        return True
    state.early_return = json.dumps({
        "error": (
            f"本会话并发委派已达上限 ({max_concurrent_delegates()}),"
            "请等待进行中的任务完成。"
        ),
        "code": "DELEGATE_CONCURRENCY",
    })
    return False


def _create_delegate_task_record(state: DelegateRunState) -> None:
    """Create the task record and pull back task_id / child_session_key (4d)."""
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


def _run_subagent_start_hooks(state: DelegateRunState) -> None:
    """Run SubagentStart hooks and prepend their context (4e, best-effort)."""
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


def _record_delegate_started_events(state: DelegateRunState) -> None:
    """Emit session-transcript events for delegate start (4f)."""
    if not state.child_session_key:
        return
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


def _init_dev_engine_state(state: DelegateRunState) -> None:
    """Initialize DevState + register DevEnginePlugin for dev delegates (4g).

    Also runs coding knowledge layer activation (D3-7 bridge).
    """
    norm = state.role.replace("_agent", "").strip().lower()
    if norm != "dev":
        return
    try:
        from butler.dev_engine.dev_tools import dev_engine_enabled
        from butler.dev_engine.dev_loop import create_dev_state

        if not dev_engine_enabled():
            return
        sk = state.child_session_key or state.session_key or "_default"
        ds = create_dev_state(task_description=state.task)

        try:
            from butler.dev_engine.coding_knowledge import (
                ExperienceLibrary,
                TheoremLibrary,
                process_task,
            )
            from butler.dev_engine.dev_state import CodingKnowledgeSummary

            import os as _os
            from butler.config import get_butler_home as _get_butler_home

            keywords = state.task.lower().split() if state.task else []
            tlib = TheoremLibrary()
            xlib_path = _os.path.join(_get_butler_home(), "coding_experiences.json")
            xlib = ExperienceLibrary.load_from_file(xlib_path, theorem_lib=tlib)
            xlib.load_seed_if_empty()
            try:
                from butler.ops.eval_config_overrides import effective_coding_knowledge_strict

                strict = effective_coding_knowledge_strict(True)
            except Exception:
                strict = True
            ctx = process_task(keywords, tlib, xlib, strict_experience=strict)
            ds.coding_knowledge = CodingKnowledgeSummary(
                mode=ctx.mode,
                activated_theorem_ids=sorted(ctx.activated_theorems.keys()),
                activated_elements=[e.value for e in ctx.activated_elements],
                experience_id=(ctx.selected_experience.id
                               if ctx.selected_experience else ""),
                experience_title=(ctx.selected_experience.title
                                  if ctx.selected_experience else ""),
            )
            ds._coding_knowledge_theorems = ctx.activated_theorems
            ds._coding_knowledge_ctx = ctx
        except Exception as exc:
            logger.debug("coding knowledge activation skipped: %s", exc)

        from butler.dev_engine.dev_tools import _active_states

        _active_states[sk] = ds

        if state.agent is not None:
            try:
                from butler.dev_engine.loop_plugin import create_dev_engine_plugin

                plugin = create_dev_engine_plugin(session_key=sk)
                plugins = getattr(state.agent, "_plugins", None)
                if plugins is not None:
                    plugins.plugins.append(plugin)
                    before_hook = getattr(plugin, "before_model", None)
                    if callable(before_hook):
                        plugins._before_llm_hooks.append(before_hook)
                    after_hook = getattr(plugin, "after_tools", None)
                    if callable(after_hook):
                        plugins._after_tools_hooks.append(after_hook)
            except Exception as exc:
                logger.debug("DevEnginePlugin registration skipped: %s", exc)

        logger.debug("DevState initialized for session %s", sk)
    except Exception as exc:  # noqa: BLE001 — best-effort init
        logger.debug("DevState initialization skipped: %s", exc)


def _record_delegate_state(state: DelegateRunState) -> None:
    """Phase 4: prefetch, semaphore, task record, hooks, transcript.

    Populates ``state.session_key``, ``state.task_id``,
    ``state.child_session_key``. Sets ``state.early_return`` if the
    concurrency semaphore is exhausted for the current session.
    """
    from butler.execution_context import get_current_session_key
    from butler.session.lifecycle import attach_turn_memory_prefetch

    attach_turn_memory_prefetch(state.agent, state.orch, state.raw_user_msg, role=state.role)
    state.session_key = str(get_current_session_key() or "").strip()
    if not _acquire_delegate_slot(state):
        return
    _create_delegate_task_record(state)
    _init_dev_engine_state(state)
    _run_subagent_start_hooks(state)
    _record_delegate_started_events(state)


def _build_async_delegate_job(state: DelegateRunState) -> Any:
    """Build the ``DelegateJob`` carrier for the async dispatch path (5a)."""
    from butler.runtime.async_delegate import push_target_from_bridge
    from butler.runtime.delegate_job import DelegateJob

    push_tgt = push_target_from_bridge(state.bridge) if state.bridge is not None else None
    return DelegateJob(
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


def _dispatch_async_delegate(state: DelegateRunState) -> str | None:
    """Schedule the delegate as a background job (5a).

    Returns the async-dispatch tool-result JSON when async dispatch is
    appropriate, otherwise ``None`` to let the caller fall through to
    the sync path.
    """
    from butler.runtime.async_delegate import (
        schedule_background_delegate,
        should_delegate_async,
    )
    from butler.runtime.delegate_job import build_async_delegate_tool_result

    if not should_delegate_async(
        bridge=state.bridge,
        depth=state.depth,
        category_meta=state.category_meta,
    ):
        return None
    schedule_background_delegate(_build_async_delegate_job(state))
    return build_async_delegate_tool_result(
        task_id=state.task_id,
        child_session_key=state.child_session_key,
        role=state.role,
        task_preview=state.task,
        category=str(state.category_meta.get("category") or state.category or ""),
    )


def _delegate_langfuse_run_callbacks(state: DelegateRunState) -> Any | None:
    """Optional nested LangFuse callbacks for sync delegate sub-loops."""
    try:
        from butler.ops.langfuse_tracer import delegate_run_callbacks

        return delegate_run_callbacks(
            parent_session_key=state.session_key,
            child_session_key=state.child_session_key or state.session_key,
            role=state.role,
            task=state.task,
            task_id=state.task_id,
        )
    except Exception as exc:  # noqa: BLE001 — best-effort tracing
        logger.debug("delegate LangFuse callbacks skipped: %s", exc)
        return None


def _run_sync_delegate(state: DelegateRunState) -> None:
    """Sync run: register, run, unregister, release slot (5b)."""
    from butler.core.delegate_semaphore import release_delegate_slot
    from butler.execution_context import use_execution_context
    from butler.runtime.delegate_registry import (
        register_delegate_loop,
        unregister_delegate_loop,
    )

    run_cbs = _delegate_langfuse_run_callbacks(state)
    try:
        with use_execution_context(
            state.orch, session_key=state.child_session_key or state.session_key
        ):
            try:
                register_delegate_loop(state.session_key, state.agent)
                if run_cbs is not None:
                    state.sync_result = state.agent.run(
                        state.user_msg, run_callbacks=run_cbs,
                    )
                else:
                    state.sync_result = state.agent.run(state.user_msg)
            finally:
                try:
                    unregister_delegate_loop(state.session_key, state.agent)
                except Exception as exc:  # noqa: BLE001 — best-effort unregister
                    logger.debug("delegate loop unregister skipped: %s", exc)
    finally:
        release_delegate_slot(state.session_key)


def _run_subagent_loop(state: DelegateRunState) -> str | None:
    """Phase 5: dispatch (async vs sync), register, run, release semaphore.

    Returns a JSON string for the async-dispatched path (caller returns
    this verbatim). For the sync path, returns ``None`` and the caller
    consumes ``state.sync_result`` then continues to :func:`_format_delegate_result`.
    """
    if (async_result := _dispatch_async_delegate(state)) is not None:
        return async_result
    _run_sync_delegate(state)
    return None


def _sync_turn_memory_for_result(state: DelegateRunState, result: Any) -> None:
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


def _build_delegate_report(
    state: DelegateRunState,
    result: Any,
    changes: list,
    issues: list,
):
    """Build the ``AgentReport`` (6b + 6d), including empty-response fallback."""
    from butler.report import AgentReport
    from butler.tools.delegate_impl import (
        _delegate_role_label,
        _delegate_task_succeeded,
    )

    success = _delegate_task_succeeded(result, changes, issues)
    role_label = _delegate_role_label(state.role)
    headline = f"{role_label}已完成任务" if success else f"{role_label}未能完成任务"
    task_preview = (state.task or "").strip()[:200]
    summary_text = (result.final_response or "").strip()
    if not summary_text:
        summary_text = (
            "DELEGATE_EMPTY_RESPONSE: 子代理未返回有效摘要。"
            "请缩小任务范围或换 category/role 后重试。"
        )
        success = False
        headline = f"{role_label}返回空结果"
    return AgentReport(
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


def _record_delegate_turn_done(state: DelegateRunState, success: bool, result: Any) -> None:
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


def _finalize_delegate_task(state: DelegateRunState, report: Any) -> None:
    """Cache report, complete task, stop hooks, bridge notify (6e)."""
    from butler.report import cache_report
    from butler.runtime.task_store import complete_task
    from butler.tools.delegate_impl import _run_subagent_stop_hooks

    cache_report(report, session_key=state.session_key)
    complete_task(
        state.task_id,
        success=report.success,
        report_headline=report.headline,
        summary=report.summary,
    )
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


def _build_result_payload(state: DelegateRunState, report: Any, result: Any) -> dict[str, Any]:
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
    _attach_dev_engine_summary(state, payload)
    return payload


def _attach_dev_engine_summary(state: DelegateRunState, payload: dict[str, Any]) -> None:
    """Attach DevState summary to delegate result when engine active (6g, DA6).

    Also extracts a candidate experience on success (CT3 closed-loop).
    """
    norm = state.role.replace("_agent", "").strip().lower()
    if norm != "dev":
        return
    try:
        from butler.dev_engine.dev_tools import _active_states, dev_engine_enabled

        if not dev_engine_enabled():
            return
        sk = state.child_session_key or state.session_key or "_default"
        ds = _active_states.pop(sk, None)
        if ds is None:
            return
        payload["dev_engine"] = {
            "phase": ds.phase.value,
            "iterations": ds.iteration,
            "edits": len(ds.edit_history),
            "fixes": ds.fix_count,
            "verify_passed": ds.verify_result.passed,
        }
        if ds.coding_knowledge.mode:
            payload["dev_engine"]["coding_knowledge"] = ds.coding_knowledge.to_dict()

        _try_extract_experience(ds, state)
    except Exception as exc:  # noqa: BLE001 — best-effort summary
        logger.debug("DevState summary attachment skipped: %s", exc)


def _try_extract_experience(ds: Any, state: DelegateRunState) -> None:
    """Best-effort: extract and persist a coding experience on task success."""
    try:
        from butler.dev_engine.dev_state import DevPhase
        if ds.phase != DevPhase.DONE or not ds.verify_result.passed:
            return

        activated = getattr(ds, "_coding_knowledge_theorems", None)
        if not activated:
            return

        snippets = [
            e.new_content for e in ds.edit_history
            if e.new_content and len(e.new_content) > 20
        ]
        if not snippets:
            return

        from butler.dev_engine.coding_knowledge import (
            ExperienceLibrary,
            TheoremLibrary,
            extract_experience_candidate,
        )

        candidate = extract_experience_candidate(
            ds.task_description, snippets, activated,
        )
        if candidate is None:
            return

        import os
        from butler.config import get_butler_home

        xlib_path = os.path.join(
            get_butler_home(), "coding_experiences.json")
        tlib = TheoremLibrary()
        xlib = ExperienceLibrary.load_from_file(xlib_path, theorem_lib=tlib)
        ok, _ = xlib.add(candidate)
        if ok:
            xlib.save_to_file(xlib_path)
            logger.debug("Extracted coding experience %s", candidate.id)
    except Exception as exc:
        logger.debug("Experience extraction skipped: %s", exc)


def peek_dev_engine_summary(session_key: str, role: str) -> dict[str, Any] | None:
    """Read DevState summary without popping (for background delegate jobs)."""
    norm = str(role or "").replace("_agent", "").strip().lower()
    if norm != "dev":
        return None
    try:
        from butler.dev_engine.dev_tools import _active_states, dev_engine_enabled

        if not dev_engine_enabled():
            return None
        ds = _active_states.get(session_key or "_default")
        if ds is None:
            return None
        summary = {
            "phase": ds.phase.value,
            "iterations": ds.iteration,
            "edits": len(ds.edit_history),
            "fixes": ds.fix_count,
            "verify_passed": ds.verify_result.passed,
        }
        if ds.coding_knowledge.mode:
            summary["coding_knowledge"] = ds.coding_knowledge.to_dict()
        return summary
    except Exception as exc:  # noqa: BLE001 — best-effort read
        logger.debug("peek dev engine summary skipped: %s", exc)
        return None


def _finalize_delegate_observability(
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

        maybe_capture_from_delegate_result(
            role=state.role,
            task=state.task,
            context=state.original_context or state.context,
            success=report.success,
            issues=issues,
            parent_session_key=state.session_key,
            child_session_key=state.child_session_key or state.session_key,
            task_id=state.task_id,
            dev_engine=dev_engine,
        )
    except Exception as exc:  # noqa: BLE001 — best-effort capture
        logger.debug("delegate failure capture skipped: %s", exc)


def _format_delegate_result(state: DelegateRunState, result: Any) -> str:
    """Phase 6: memory sync, report, cache, complete_task, hooks, payload."""
    from butler.tools.delegate_impl import (
        _extract_changes_from_messages,
        _extract_issues_from_messages,
    )

    _sync_turn_memory_for_result(state, result)
    changes = _extract_changes_from_messages(result.messages)
    issues = _extract_issues_from_messages(result.messages)
    report = _build_delegate_report(state, result, changes, issues)
    _record_delegate_turn_done(state, report.success, result)
    _finalize_delegate_task(state, report)
    payload = _build_result_payload(state, report, result)
    _finalize_delegate_observability(state, report, issues, payload)
    return json.dumps(payload, ensure_ascii=False)

"""Delegate phases 3–4 — user message and pre-run bookkeeping (ENG-2)."""

from __future__ import annotations

import json
import logging
from typing import Any

from butler.tools.delegate_run_state import DelegateRunState

logger = logging.getLogger(__name__)


def build_user_message(state: DelegateRunState) -> None:
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


def acquire_delegate_slot(state: DelegateRunState) -> bool:
    """Acquire a concurrency slot for the current session (4c)."""
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


def create_delegate_task_record(state: DelegateRunState) -> None:
    """Create the task record and pull back task_id / child_session_key (4d)."""
    from butler.runtime.task_store import create_task, delegate_group_id
    from butler.tools.delegate_role_guard import apply_user_role_override

    apply_user_role_override(state)

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


def run_subagent_start_hooks(state: DelegateRunState) -> None:
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


def record_delegate_started_events(state: DelegateRunState) -> None:
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


def init_dev_engine_state(state: DelegateRunState) -> None:
    """Initialize DevState + register DevEnginePlugin for dev delegates (4g)."""
    from butler.dev_engine.delegate_init import init_dev_engine_state_for_delegate

    init_dev_engine_state_for_delegate(state)


def prepare_b9_benchmark_workspace(state: DelegateRunState) -> None:
    from butler.dev_engine.delegate_workspace import prepare_b9_benchmark_workspace

    prepare_b9_benchmark_workspace(state)


def prepare_isolated_workspace_read_state(state: DelegateRunState) -> None:
    from butler.dev_engine.delegate_workspace import prepare_isolated_workspace_read_state

    prepare_isolated_workspace_read_state(state)


def record_delegate_state(state: DelegateRunState) -> None:
    """Phase 4: prefetch, semaphore, task record, hooks, transcript."""
    from butler.execution_context import get_current_session_key
    from butler.session.lifecycle import attach_turn_memory_prefetch

    attach_turn_memory_prefetch(state.agent, state.orch, state.raw_user_msg, role=state.role)
    state.session_key = str(get_current_session_key() or "").strip()
    if not acquire_delegate_slot(state):
        return
    create_delegate_task_record(state)
    prepare_b9_benchmark_workspace(state)
    prepare_isolated_workspace_read_state(state)
    init_dev_engine_state(state)
    run_subagent_start_hooks(state)
    record_delegate_started_events(state)


__all__ = [
    "acquire_delegate_slot",
    "build_user_message",
    "create_delegate_task_record",
    "init_dev_engine_state",
    "prepare_b9_benchmark_workspace",
    "prepare_isolated_workspace_read_state",
    "record_delegate_started_events",
    "record_delegate_state",
    "run_subagent_start_hooks",
]

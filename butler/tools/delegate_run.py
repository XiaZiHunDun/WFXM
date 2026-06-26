"""Delegate phase 5 — async vs sync subagent execution (ENG-2)."""

from __future__ import annotations

import logging
from typing import Any

from butler.tools.delegate_run_state import DelegateRunState

logger = logging.getLogger(__name__)


def build_async_delegate_job(state: DelegateRunState) -> Any:
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


def dispatch_async_delegate(state: DelegateRunState) -> str | None:
    """Schedule the delegate as a background job (5a)."""
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
    schedule_background_delegate(build_async_delegate_job(state))
    return build_async_delegate_tool_result(
        task_id=state.task_id,
        child_session_key=state.child_session_key,
        role=state.role,
        task_preview=state.task,
        category=str(state.category_meta.get("category") or state.category or ""),
    )


def delegate_langfuse_run_callbacks(state: DelegateRunState) -> Any | None:
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


def run_sync_delegate(state: DelegateRunState) -> None:
    """Sync run: register, run, unregister, release slot (5b)."""
    from butler.core.delegate_semaphore import release_delegate_slot
    from butler.execution_context import use_execution_context
    from butler.runtime.delegate_registry import (
        register_delegate_loop,
        unregister_delegate_loop,
    )

    run_cbs = delegate_langfuse_run_callbacks(state)
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


def run_subagent_loop(state: DelegateRunState) -> str | None:
    """Phase 5: dispatch (async vs sync), register, run, release semaphore."""
    if (async_result := dispatch_async_delegate(state)) is not None:
        return async_result
    run_sync_delegate(state)
    return None


__all__ = [
    "build_async_delegate_job",
    "delegate_langfuse_run_callbacks",
    "dispatch_async_delegate",
    "run_subagent_loop",
    "run_sync_delegate",
]

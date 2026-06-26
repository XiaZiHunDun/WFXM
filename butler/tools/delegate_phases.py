"""Phase helpers extracted from ``_tool_delegate_task`` (R1-5 split, ENG-2).

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

ENG-2 (2026-06): implementation lives in focused submodules; this module
is a stable re-export facade for ``delegate_impl`` and tests.
"""

from __future__ import annotations

import logging
from typing import Any

from butler.tools.delegate_prepare import (
    apply_category_resolver as _apply_category_resolver,
    build_handoff_block_text as _build_handoff_block_text,
    check_delegate_depth as _check_delegate_depth,
    infer_delegate_category as _infer_delegate_category,
    inject_handoff_block as _inject_handoff_block,
    inject_production_playbook_bridge as _inject_production_playbook_bridge,
    inject_verify_checklist as _inject_verify_checklist,
    prepare_delegate_task as _prepare_delegate_task,
)
from butler.tools.delegate_record import (
    acquire_delegate_slot as _acquire_delegate_slot,
    build_user_message as _build_user_message,
    create_delegate_task_record as _create_delegate_task_record,
    init_dev_engine_state as _init_dev_engine_state,
    prepare_b9_benchmark_workspace as _prepare_b9_benchmark_workspace,
    prepare_isolated_workspace_read_state as _prepare_isolated_workspace_read_state,
    record_delegate_started_events as _record_delegate_started_events,
    record_delegate_state as _record_delegate_state,
    run_subagent_start_hooks as _run_subagent_start_hooks,
)
from butler.tools.delegate_report import (
    build_delegate_report as _build_delegate_report,
    build_result_payload as _build_result_payload,
    finalize_delegate_observability as _finalize_delegate_observability,
    finalize_delegate_task as _finalize_delegate_task,
    format_delegate_result as _format_delegate_result,
    peek_dev_engine_summary,
    record_delegate_turn_done as _record_delegate_turn_done,
    sync_turn_memory_for_result as _sync_turn_memory_for_result,
)
from butler.tools.delegate_run import (
    build_async_delegate_job as _build_async_delegate_job,
    delegate_langfuse_run_callbacks as _delegate_langfuse_run_callbacks,
    dispatch_async_delegate as _dispatch_async_delegate,
    run_subagent_loop as _run_subagent_loop,
    run_sync_delegate as _run_sync_delegate,
)
from butler.tools.delegate_run_state import DelegateRunState
from butler.tools.delegate_subagent import (
    apply_cache_safe_prompt as _apply_cache_safe_prompt,
    apply_subagent_tool_filters as _apply_subagent_tool_filters,
    attach_agents_md_context as _attach_agents_md_context,
    build_subagent_tools as _build_subagent_tools,
    configure_subagent_policy as _configure_subagent_policy,
    create_project_agent_loop as _create_project_agent_loop,
    inject_dev_engine_prompt as _inject_dev_engine_prompt,
    inject_workspace_root_context as _inject_workspace_root_context,
    resolve_subagent as _resolve_subagent,
)

logger = logging.getLogger(__name__)

__all__ = [
    "DelegateRunState",
    "_acquire_delegate_slot",
    "_apply_cache_safe_prompt",
    "_apply_category_resolver",
    "_apply_subagent_tool_filters",
    "_attach_agents_md_context",
    "_attach_dev_engine_summary",
    "_build_async_delegate_job",
    "_build_delegate_report",
    "_build_handoff_block_text",
    "_build_result_payload",
    "_build_subagent_tools",
    "_build_user_message",
    "_check_delegate_depth",
    "_configure_subagent_policy",
    "_create_delegate_task_record",
    "_create_project_agent_loop",
    "_delegate_langfuse_run_callbacks",
    "_dispatch_async_delegate",
    "_finalize_delegate_observability",
    "_finalize_delegate_task",
    "_format_delegate_result",
    "_infer_delegate_category",
    "_init_dev_engine_state",
    "_inject_dev_engine_prompt",
    "_inject_handoff_block",
    "_inject_production_playbook_bridge",
    "_inject_verify_checklist",
    "_inject_workspace_root_context",
    "_prepare_b9_benchmark_workspace",
    "_prepare_delegate_task",
    "_prepare_isolated_workspace_read_state",
    "_record_delegate_started_events",
    "_record_delegate_state",
    "_record_delegate_turn_done",
    "_resolve_subagent",
    "_run_subagent_loop",
    "_run_subagent_start_hooks",
    "_run_sync_delegate",
    "_sync_turn_memory_for_result",
    "peek_dev_engine_summary",
]


def _attach_dev_engine_summary(state: DelegateRunState, payload: dict[str, Any]) -> None:
    from butler.dev_engine.delegate_finalize import attach_dev_engine_summary

    attach_dev_engine_summary(state, payload)

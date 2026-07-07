"""Delegate phase 2 — subagent loop construction (ENG-2)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from butler.tools.delegate_run_state import DelegateRunState
from butler.tools.delegate_subagent_ops import merge_agents_md_context_safe
from butler.delegate.subagent_permissions import filter_tools_for_subagent
from butler.tools.project_tools import get_tool_definitions_for_project
from butler.core.delegate_context import child_callbacks, get_parent_callbacks
from butler.tools.delegate_impl import _safe_dispatch
from butler.core.cache_safe_delegate import apply_cache_safe_system_prompt, delegate_diagnostics
from butler.core.delegate_context import get_parent_messages, get_parent_system_prompt
from butler.delegate.policy import resolve_delegate_max_iterations
from butler.tools.delegate_subagent_ops import apply_one_tool_per_iteration_safe
from butler.tools.delegate_subagent_ops import inject_dev_engine_prompt_safe
from butler.execution_context import get_current_session_key
from butler.tools.delegate_impl import _orchestrator_for_tool


def attach_agents_md_context(state: DelegateRunState) -> None:
    """Merge ``AGENTS.md`` into context for the current project (2b)."""

    merge_agents_md_context_safe(state)


def build_subagent_tools(state: DelegateRunState) -> None:
    """Populate ``state.tools`` and ``state.delegated_tools`` (2c base)."""

    state.tools = get_tool_definitions_for_project(state.project, role=state.role)
    workspace = Path(state.project.workspace) if state.project is not None else None
    state.delegated_tools = filter_tools_for_subagent(
        state.tools,
        workspace=workspace,
        role=state.role,
    )


def apply_subagent_tool_filters(state: DelegateRunState) -> None:
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


def create_project_agent_loop(state: DelegateRunState) -> None:
    """Create the child agent loop with safe dispatch + child callbacks (2d)."""

    parent_cb = get_parent_callbacks()
    state.agent = state.orch.create_project_agent_loop(
        role=state.role,
        tools=state.delegated_tools,
        tool_dispatcher=lambda name, args: _safe_dispatch(name, args, state.depth + 1),
        callbacks=child_callbacks(parent_cb),
        session_key=state.child_session_key or state.session_key,
    )


def apply_cache_safe_prompt(state: DelegateRunState) -> None:
    """Merge parent system prompt + record cache diagnostics (2e)."""

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


def configure_subagent_policy(state: DelegateRunState) -> None:
    """Apply max-iterations + one-tool-per-iter policy (2f)."""

    state.agent.config.max_iterations = resolve_delegate_max_iterations(state.category_meta)

    apply_one_tool_per_iteration_safe(state)


def inject_dev_engine_prompt(state: DelegateRunState) -> None:
    """Append dev engine system prompt when role=dev and engine enabled (2g)."""
    norm = state.role.replace("_agent", "").strip().lower()
    if norm != "dev":
        return

    inject_dev_engine_prompt_safe(state)


def inject_workspace_root_context(state: DelegateRunState) -> None:
    """Prepend deterministic workspace-relative path rules for sub-agents."""
    if state.project is None:
        return
    try:
        ws = Path(state.project.workspace).resolve()
    except (TypeError, ValueError, OSError):
        return
    if not ws.is_dir():
        return
    marker = "## 工作区（必守）"
    if marker in str(state.context or ""):
        return
    dir_name = ws.name
    block = (
        f"{marker}\n"
        f"- 项目 workspace 根目录：`{ws}`\n"
        "- 所有 read_file / write_file / patch 路径必须**相对此根**（例：`docs/foo.md`）\n"
        f"- **禁止** `{dir_name}/docs/...`、项目目录名前缀、或 workspace 外的绝对路径\n"
    )
    state.context = f"{block}\n{state.context}".strip() if state.context else block


def resolve_subagent(state: DelegateRunState) -> None:
    """Phase 2: build the project agent loop with cache-safe prompt."""

    state.orch = _orchestrator_for_tool(channel="cli")
    parent_sk = str(get_current_session_key() or "").strip()
    state.project = state.orch.project_manager.get_current(session_key=parent_sk)
    inject_workspace_root_context(state)
    attach_agents_md_context(state)
    build_subagent_tools(state)
    apply_subagent_tool_filters(state)
    create_project_agent_loop(state)
    inject_dev_engine_prompt(state)
    apply_cache_safe_prompt(state)
    configure_subagent_policy(state)
    state.agent.reset()


__all__ = [
    "apply_cache_safe_prompt",
    "apply_subagent_tool_filters",
    "attach_agents_md_context",
    "build_subagent_tools",
    "configure_subagent_policy",
    "create_project_agent_loop",
    "inject_dev_engine_prompt",
    "inject_workspace_root_context",
    "resolve_subagent",
]

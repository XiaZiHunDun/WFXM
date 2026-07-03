"""Delegate subagent loop best-effort helpers (P0-A)."""

from __future__ import annotations

from pathlib import Path

from butler.core.best_effort import safe_best_effort
from butler.tools.delegate_run_state import DelegateRunState


def merge_agents_md_context_safe(state: DelegateRunState) -> None:
    if state.project is None:
        return

    def _run() -> None:
        from butler.agents_md import merge_agent_md_into_context

        state.context = merge_agent_md_into_context(
            Path(state.project.workspace),
            state.role,
            state.context,
        )

    safe_best_effort(_run, label="delegate_subagent.agents_md", default=None)


def apply_one_tool_per_iteration_safe(state: DelegateRunState) -> None:
    def _run() -> None:
        from butler.delegate.policy import delegate_one_tool_per_iteration

        if delegate_one_tool_per_iteration():
            state.agent.config.enable_parallel_tools = False
            state.agent.diagnostics["delegate_one_tool_per_iteration"] = True

    safe_best_effort(_run, label="delegate_subagent.one_tool_policy", default=None)


def inject_dev_engine_prompt_safe(state: DelegateRunState) -> None:
    def _run() -> None:
        from butler.agent_profiles import get_dev_agent_prompt

        enhanced = get_dev_agent_prompt()
        if enhanced and len(enhanced) > len(state.agent.system_prompt):
            state.agent.system_prompt = enhanced

    safe_best_effort(_run, label="delegate_subagent.dev_prompt", default=None)

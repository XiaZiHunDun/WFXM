"""AgentLoop factory best-effort helpers (P0-A)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from butler.core.best_effort import safe_best_effort

if TYPE_CHECKING:
    from butler.orchestrator import ButlerOrchestrator


def apply_project_plugins_safe(orch: "ButlerOrchestrator", session_key: str) -> None:
    def _run() -> None:
        from butler.project.plugins import apply_project_plugins

        proj = orch.project_manager.get_current(session_key=session_key)
        apply_project_plugins(proj)

    safe_best_effort(_run, label="loop_factory.project_plugins", default=None)


def append_plan_mode_appendix_safe(session_key: str, system_prompt: str) -> str:
    def _run() -> str:
        from butler.plan.mode import is_plan_mode, load_plan_mode_system_appendix

        if is_plan_mode(session_key):
            return system_prompt.rstrip() + "\n\n" + load_plan_mode_system_appendix()
        return system_prompt

    result = safe_best_effort(
        _run,
        label="loop_factory.plan_mode_appendix",
        default=system_prompt,
    )
    return str(result) if isinstance(result, str) else system_prompt

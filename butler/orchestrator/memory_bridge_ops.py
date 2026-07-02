"""Memory bridge best-effort helpers (P0-A)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from butler.core.best_effort import safe_best_effort

if TYPE_CHECKING:
    from butler.orchestrator import ButlerOrchestrator

logger = logging.getLogger(__name__)


def refresh_project_facts_safe(project_memory: Any) -> None:
    def _run() -> None:
        project_memory.refresh_facts()

    safe_best_effort(_run, label="memory_bridge.refresh_facts", default=None)


def close_tenant_memory_safe(mem: Any) -> None:
    def _run() -> None:
        mem.close()

    safe_best_effort(_run, label="memory_bridge.close_tenant_memory", default=None)


def clear_memory_degradation_safe() -> None:
    def _run() -> None:
        from butler.ops.degradation_registry import clear_degradation

        clear_degradation("memory")

    safe_best_effort(_run, label="memory_bridge.clear_degradation", default=None)


def register_memory_degradation_safe(detail: str) -> None:
    def _run() -> None:
        from butler.ops.degradation_registry import register_degradation

        register_degradation("memory", "初始化失败", detail=detail[:200])

    safe_best_effort(_run, label="memory_bridge.register_degradation", default=None)


def initialize_memory_provider_loud(orch: ButlerOrchestrator) -> None:
    """Initialize memory provider; on failure set orch offline and register degradation."""
    try:
        from butler.memory.facade import ButlerMemoryService

        provider = ButlerMemoryService()
        provider.link_orchestrator(orch)
        provider.initialize(
            session_id=f"{orch.channel}:{orch.user_id}",
            user_id=orch.user_id,
        )
        orch.memory_provider = provider
        orch.memory_offline = False
        orch._memory_init_error = ""
        clear_memory_degradation_safe()
    except Exception as exc:
        logger.error(
            "Butler memory provider unavailable: %s",
            exc,
            exc_info=exc,
        )
        orch.memory_provider = None
        orch.memory_offline = True
        orch._memory_init_error = f"{type(exc).__name__}: {exc}"
        register_memory_degradation_safe(orch._memory_init_error)


def refresh_memory_provider_branches_safe(provider: Any) -> None:
    def _run() -> None:
        if hasattr(provider, "_turn_buffer"):
            provider._turn_buffer.clear()
        if hasattr(provider, "_reload_butler_global"):
            provider._reload_butler_global()
        if hasattr(provider, "_reload_project_branch"):
            provider._reload_project_branch()

    safe_best_effort(_run, label="memory_bridge.refresh_provider", default=None)


def design_context_block_safe(
    workspace: Path,
    *,
    design_preset: str = "",
) -> str:
    def _run() -> str:
        from butler.core.design_md_sections import build_design_context_block

        return str(
            build_design_context_block(workspace, design_preset=design_preset) or ""
        ).strip()

    result = safe_best_effort(_run, label="memory_bridge.design_context", default="")
    return str(result or "").strip()


def outcome_context_block_safe(workspace: Path, *, project: str) -> str:
    def _run() -> str:
        from butler.experiments.outcomes import format_context_for_prompt

        return str(format_context_for_prompt(workspace, project=project) or "").strip()

    result = safe_best_effort(_run, label="memory_bridge.outcome_context", default="")
    return str(result or "").strip()

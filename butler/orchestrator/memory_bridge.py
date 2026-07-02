"""Memory provider and project-memory wiring (ENG-12)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from butler.orchestrator import ButlerOrchestrator

from butler.memory import ButlerMemory, ProjectMemory


def reload_project_memory(orch: ButlerOrchestrator) -> None:
    from butler.orchestrator.memory_bridge_ops import refresh_project_facts_safe

    proj = orch.project_manager.get_current()
    if proj is None:
        orch._project_memory = None
    else:
        orch._project_memory = ProjectMemory(proj.workspace)
        if orch._project_memory is not None:
            refresh_project_facts_safe(orch._project_memory)


def get_butler_memory(orch: ButlerOrchestrator) -> ButlerMemory:
    from butler.orchestrator.memory_bridge_ops import close_tenant_memory_safe
    from butler.tenant import resolve_tenant_for_project

    tid = resolve_tenant_for_project(
        orch.project_manager.get_current(),
        orch._settings,
    )
    with orch._memory_lock:
        mem = orch._memory_by_tenant.get(tid)
        if mem is None:
            if len(orch._memory_by_tenant) >= 64:
                oldest = next(iter(orch._memory_by_tenant))
                evicted = orch._memory_by_tenant.pop(oldest, None)
                if evicted is not None:
                    close_tenant_memory_safe(evicted)
            mem = ButlerMemory(orch._settings.butler_home, tenant_id=tid)
            orch._memory_by_tenant[tid] = mem
    return mem


def initialize_memory_provider(orch: ButlerOrchestrator) -> None:
    from butler.orchestrator.memory_bridge_ops import initialize_memory_provider_loud

    initialize_memory_provider_loud(orch)


def refresh_memory_provider_for_project_switch(orch: ButlerOrchestrator) -> None:
    from butler.orchestrator.memory_bridge_ops import refresh_memory_provider_branches_safe

    provider = getattr(orch, "memory_provider", None)
    if provider is None:
        return
    refresh_memory_provider_branches_safe(provider)


def build_memory_context(orch: ButlerOrchestrator, *, for_role: str = "default") -> str:
    from pathlib import Path

    from butler.orchestrator.memory_bridge_ops import (
        design_context_block_safe,
        outcome_context_block_safe,
    )

    current = orch.project_manager.current_project or ""
    chunks: list[str] = []

    bm = get_butler_memory(orch).get_system_context(current)
    chunks.append(bm)

    if orch._project_memory is not None:
        pm_txt = orch._project_memory.get_context_for_agent(for_role)
        chunks.append(f"## 当前项目记忆\n{pm_txt}")

    proj = orch.project_manager.get_current()
    if proj is not None:
        design_block = design_context_block_safe(
            Path(proj.workspace),
            design_preset=str(getattr(proj, "design_preset", "") or ""),
        )
        if design_block:
            chunks.append(design_block)

        outcome_block = outcome_context_block_safe(
            Path(proj.workspace),
            project=str(proj.name or current or ""),
        )
        if outcome_block:
            chunks.append(outcome_block)

    return "\n\n".join(c for c in chunks if c and str(c).strip())


__all__ = [
    "build_memory_context",
    "get_butler_memory",
    "initialize_memory_provider",
    "refresh_memory_provider_for_project_switch",
    "reload_project_memory",
]

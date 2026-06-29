"""Memory provider and project-memory wiring (ENG-12)."""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from butler.orchestrator import ButlerOrchestrator

from butler.memory import ButlerMemory, ProjectMemory

logger = logging.getLogger(__name__)


def reload_project_memory(orch: ButlerOrchestrator) -> None:
    proj = orch.project_manager.get_current()
    if proj is None:
        orch._project_memory = None
    else:
        orch._project_memory = ProjectMemory(proj.workspace)
        try:
            orch._project_memory.refresh_facts()
        except Exception as exc:
            logger.debug("Project facts refresh skipped: %s", exc)


def get_butler_memory(orch: ButlerOrchestrator) -> ButlerMemory:
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
                    try:
                        evicted.close()
                    except Exception as exc:
                        logger.debug("tenant memory close on evict skipped: %s", exc)
            mem = ButlerMemory(orch._settings.butler_home, tenant_id=tid)
            orch._memory_by_tenant[tid] = mem
    return mem


def initialize_memory_provider(orch: ButlerOrchestrator) -> None:
    from butler.memory.facade import ButlerMemoryService

    try:
        provider = ButlerMemoryService()
        provider.link_orchestrator(orch)
        provider.initialize(
            session_id=f"{orch.channel}:{orch.user_id}",
            user_id=orch.user_id,
        )
        orch.memory_provider = provider
        orch.memory_offline = False
        orch._memory_init_error = ""
        try:
            from butler.ops.degradation_registry import clear_degradation

            clear_degradation("memory")
        except Exception:
            pass
    except Exception as exc:
        logger.error(
            "Butler memory provider unavailable: %s",
            exc,
            exc_info=exc,
        )
        orch.memory_provider = None
        orch.memory_offline = True
        orch._memory_init_error = f"{type(exc).__name__}: {exc}"
        try:
            from butler.ops.degradation_registry import register_degradation

            register_degradation(
                "memory",
                "初始化失败",
                detail=orch._memory_init_error[:200],
            )
        except Exception:
            pass


def refresh_memory_provider_for_project_switch(orch: ButlerOrchestrator) -> None:
    provider = getattr(orch, "memory_provider", None)
    if provider is None:
        return
    try:
        if hasattr(provider, "_turn_buffer"):
            provider._turn_buffer.clear()
        if hasattr(provider, "_reload_butler_global"):
            provider._reload_butler_global()
        if hasattr(provider, "_reload_project_branch"):
            provider._reload_project_branch()
    except Exception as exc:
        logger.debug("Butler memory provider refresh skipped: %s", exc)


def build_memory_context(orch: ButlerOrchestrator, *, for_role: str = "default") -> str:
    current = orch.project_manager.current_project or ""
    chunks: list[str] = []

    bm = get_butler_memory(orch).get_system_context(current)
    chunks.append(bm)

    if orch._project_memory is not None:
        pm_txt = orch._project_memory.get_context_for_agent(for_role)
        chunks.append(f"## 当前项目记忆\n{pm_txt}")

    proj = orch.project_manager.get_current()
    if proj is not None:
        try:
            from butler.core.design_md_sections import build_design_context_block

            design_block = build_design_context_block(
                Path(proj.workspace),
                design_preset=str(getattr(proj, "design_preset", "") or ""),
            )
            if design_block.strip():
                chunks.append(design_block.strip())
        except Exception as exc:
            logger.debug("DESIGN context inject skipped: %s", exc)

    try:
        from butler.experiments.outcomes import format_context_for_prompt

        if proj is not None:
            outcome_block = format_context_for_prompt(
                Path(proj.workspace),
                project=str(proj.name or current or ""),
            )
            if outcome_block.strip():
                chunks.append(outcome_block.strip())
    except Exception as exc:
        logger.debug("Outcome context inject skipped: %s", exc)

    return "\n\n".join(c for c in chunks if c and str(c).strip())


__all__ = [
    "build_memory_context",
    "get_butler_memory",
    "initialize_memory_provider",
    "refresh_memory_provider_for_project_switch",
    "reload_project_memory",
]

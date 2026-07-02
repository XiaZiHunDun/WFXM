"""Skill tool bridge best-effort helpers (P0-A)."""

from __future__ import annotations

from butler.core.best_effort import safe_best_effort


def skill_preferred_tools_safe(names: list[str]) -> set[str]:
    def _run() -> set[str]:
        from butler.execution_context import get_current_orchestrator

        orch = get_current_orchestrator()
        if orch is None or orch._skill_router is None:
            return set()
        pt = orch._skill_router.get_preferred_tools_for_names(names)
        if pt:
            _inc_pointer_pin_safe(len(pt), "injected_skill")
        return set(pt)

    result = safe_best_effort(_run, label="skill_tool_bridge.injected_skill", default=set())
    return result if isinstance(result, set) else set()


def experience_pinned_tools_safe(query: str) -> tuple[set[str], list[str]]:
    def _run() -> tuple[set[str], list[str]]:
        from butler.execution_context import get_current_orchestrator
        from butler.session.memory_prefetch import peek_experience_hits
        from butler.skills.experience_pointers import (
            extract_mcp_refs_from_hits,
            extract_tool_refs_from_hits,
            resolve_mcp_refs_to_registered,
        )
        from butler.skills.injection_policy import extract_skill_refs_from_hits

        orch = get_current_orchestrator()
        if orch is None:
            return set(), []
        hits = peek_experience_hits(orch, query)
        if not hits:
            return set(), []
        tools = set(extract_tool_refs_from_hits(hits))
        if tools:
            _inc_pointer_pin_safe(len(tools), "experience_tool")
        skill_refs = extract_skill_refs_from_hits(hits)
        router = getattr(orch, "_skill_router", None)
        if skill_refs and router is not None:
            skill_pt = router.get_preferred_tools_for_names(skill_refs)
            tools.update(skill_pt)
            if skill_pt:
                _inc_pointer_pin_safe(len(skill_pt), "experience_skill")
        mcp_refs = extract_mcp_refs_from_hits(hits)
        mcp_names = resolve_mcp_refs_to_registered(mcp_refs) if mcp_refs else []
        return tools, mcp_names

    result = safe_best_effort(
        _run,
        label="skill_tool_bridge.experience_pins",
        default=(set(), []),
    )
    if isinstance(result, tuple) and len(result) == 2:
        tools, mcp = result
        return (
            set(tools) if isinstance(tools, set) else set(),
            list(mcp) if isinstance(mcp, list) else [],
        )
    return set(), []


def _inc_pointer_pin_safe(count: int, source: str) -> None:
    if count <= 0:
        return

    def _run() -> None:
        from butler.ops.runtime_metrics import inc

        inc("execution_pointer_pin", value=count, labels={"source": source})

    safe_best_effort(_run, label="skill_tool_bridge.pointer_pin", default=None)

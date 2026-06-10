"""Bridge between skill routing and tool selection.

When a skill declares `preferred_tools` in its frontmatter, those tools
are pinned during tool selection so they won't be dropped by the selector.

Experience pointers (``skill:`` / ``tool:`` / ``mcp:``) pin tools even when
skill bodies are skipped by the retrieval trust cascade.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

_SKILL_HEADER_RE = re.compile(r"^###\s+`([^`]+)`")
_SKILL_SECTION_MARKER = "## 相关知识"


def extract_injected_skill_names(augmented_message: str) -> list[str]:
    """Parse skill names from injected ``### `name``` headers under 相关知识."""
    if _SKILL_SECTION_MARKER not in augmented_message:
        return []
    in_section = False
    names: list[str] = []
    seen: set[str] = set()
    for line in augmented_message.splitlines():
        stripped = line.strip()
        if stripped.startswith(_SKILL_SECTION_MARKER):
            in_section = True
            continue
        if in_section and line.startswith("## ") and not line.startswith("### "):
            break
        if not in_section:
            continue
        m = _SKILL_HEADER_RE.match(stripped)
        if not m:
            continue
        name = m.group(1).strip()
        if name and name not in seen:
            seen.add(name)
            names.append(name)
    return names


def extract_skill_preferred_tools(augmented_message: str) -> set[str]:
    """Extract preferred_tools from skill sections injected into the user message.

    The orchestrator injects skill context as:
      ## 相关知识（Butler Skill）
      ### `skill-name` (相关性 0.9)
      ...skill body with optional preferred_tools frontmatter...

    We parse the injected skill names, then look up their preferred_tools
    from the orchestrator's skill router.
    """
    tools: set[str] = set()
    names = extract_injected_skill_names(augmented_message)
    if not names:
        return tools

    try:
        from butler.execution_context import get_current_orchestrator

        orch = get_current_orchestrator()
        if orch is None or orch._skill_router is None:
            return tools

        pt = orch._skill_router.get_preferred_tools_for_names(names)
        tools.update(pt)
        if pt:
            try:
                from butler.ops.runtime_metrics import inc

                inc(
                    "execution_pointer_pin",
                    value=len(pt),
                    labels={"source": "injected_skill"},
                )
            except Exception:  # noqa: BLE001 — metrics optional
                pass
    except Exception as exc:
        logger.debug("Skill preferred_tools extraction failed: %s", exc)

    return tools


def resolve_experience_pinned_tools(query: str) -> tuple[set[str], list[str]]:
    """Pin builtin tools and MCP names from experience hits (no skill body required).

    Returns ``(builtin_tool_names, mcp_registered_names)``.
    """
    tools: set[str] = set()
    mcp_names: list[str] = []
    q = (query or "").strip()
    if not q:
        return tools, mcp_names

    try:
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
            return tools, mcp_names

        hits = peek_experience_hits(orch, q)
        if not hits:
            return tools, mcp_names

        exp_tools = extract_tool_refs_from_hits(hits)
        tools.update(exp_tools)
        if exp_tools:
            _inc_pointer_pin(len(exp_tools), "experience_tool")

        skill_refs = extract_skill_refs_from_hits(hits)
        router = getattr(orch, "_skill_router", None)
        if skill_refs and router is not None:
            skill_pt = router.get_preferred_tools_for_names(skill_refs)
            tools.update(skill_pt)
            if skill_pt:
                _inc_pointer_pin(len(skill_pt), "experience_skill")

        mcp_refs = extract_mcp_refs_from_hits(hits)
        if mcp_refs:
            mcp_names = resolve_mcp_refs_to_registered(mcp_refs)
    except Exception as exc:
        logger.debug("Experience pinned tools resolution failed: %s", exc)

    return tools, mcp_names


def _inc_pointer_pin(count: int, source: str) -> None:
    if count <= 0:
        return
    try:
        from butler.ops.runtime_metrics import inc

        inc("execution_pointer_pin", value=count, labels={"source": source})
    except Exception:  # noqa: BLE001 — metrics optional
        pass


def collect_pinned_tools(user_content: str) -> tuple[set[str], list[str]]:
    """Merge injected-skill and experience pointer pins for tool selection."""
    builtin = extract_skill_preferred_tools(user_content)
    exp_tools, exp_mcp = resolve_experience_pinned_tools(user_content)
    return builtin | exp_tools, exp_mcp

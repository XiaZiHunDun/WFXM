"""Bridge between skill routing and tool selection.

When a skill declares `preferred_tools` in its frontmatter, those tools
are pinned during tool selection so they won't be dropped by the selector.

Experience pointers (``skill:`` / ``tool:`` / ``mcp:``) pin tools even when
skill bodies are skipped by the retrieval trust cascade.
"""

from __future__ import annotations

import re
from typing import cast

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

    from butler.core.skill_tool_bridge_ops import skill_preferred_tools_safe

    return cast(set[str], skill_preferred_tools_safe(names))


def resolve_experience_pinned_tools(query: str) -> tuple[set[str], list[str]]:
    """Pin builtin tools and MCP names from experience hits (no skill body required).

    Returns ``(builtin_tool_names, mcp_registered_names)``.
    """
    tools: set[str] = set()
    mcp_names: list[str] = []
    q = (query or "").strip()
    if not q:
        return tools, mcp_names

    from butler.core.skill_tool_bridge_ops import experience_pinned_tools_safe

    return cast(tuple[set[str], list[str]], experience_pinned_tools_safe(q))


def collect_pinned_tools(user_content: str) -> tuple[set[str], list[str]]:
    """Merge injected-skill and experience pointer pins for tool selection."""
    builtin = extract_skill_preferred_tools(user_content)
    exp_tools, exp_mcp = resolve_experience_pinned_tools(user_content)
    return builtin | exp_tools, exp_mcp

"""Bridge between skill routing and tool selection.

When a skill declares `preferred_tools` in its frontmatter, those tools
are pinned during tool selection so they won't be dropped by the selector.
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

_SKILL_TOOLS_PATTERN = re.compile(
    r"##\s+相关知识.*?###\s+`([^`]+)`",
    re.DOTALL,
)


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
    if "## 相关知识" not in augmented_message:
        return tools

    try:
        from butler.execution_context import get_current_orchestrator

        orch = get_current_orchestrator()
        if orch is None or orch._skill_router is None:
            return tools

        pt = orch._skill_router.get_preferred_tools(augmented_message)
        tools.update(pt)
    except Exception as exc:
        logger.debug("Skill preferred_tools extraction failed: %s", exc)

    return tools

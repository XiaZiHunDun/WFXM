"""Normalize tool calls from model output (Hermes run_agent L6047+)."""

from __future__ import annotations

import logging
import re
from difflib import get_close_matches

from butler.transport.types import ToolCall

logger = logging.getLogger(__name__)

BUTLER_TOOL_NAMES = frozenset({
    "read_file",
    "write_file",
    "patch",
    "terminal",
    "search_files",
    "list_directory",
    "skills_list",
    "skill_view",
    "delegate_task",
})

MAX_CONCURRENT_DELEGATES = 2

_EMPTY_RETRY_NUDGE = (
    "Your previous response contained only internal reasoning with no visible reply "
    "or tool calls. Please provide a helpful response to the user or call tools as needed."
)

_TRUNCATION_NUDGE = (
    "Your previous response was cut off due to length limits. Continue from where you "
    "left off and complete the task."
)


def repair_tool_name(name: str, valid_names: set[str] | None = None) -> str | None:
    """Map malformed tool names to Butler registry names."""
    valid = valid_names or BUTLER_TOOL_NAMES
    if not name:
        return None
    if name in valid:
        return name

    def _norm(s: str) -> str:
        return s.lower().replace("-", "_").replace(" ", "_")

    n = _norm(name)
    if n in valid:
        return n

    camel = re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()
    if camel in valid:
        return camel
    for suffix in ("_tool", "-tool", "tool"):
        if camel.endswith(suffix):
            base = camel[: -len(suffix)].rstrip("_")
            if base in valid:
                return base

    matches = get_close_matches(n, list(valid), n=1, cutoff=0.7)
    if matches:
        return matches[0]
    matches = get_close_matches(camel, list(valid), n=1, cutoff=0.7)
    return matches[0] if matches else None


def normalize_tool_calls(
    tool_calls: list[ToolCall],
    valid_names: set[str] | None = None,
) -> list[ToolCall]:
    """Deduplicate, repair names, cap delegate_task count."""
    valid = valid_names or BUTLER_TOOL_NAMES
    seen: set[tuple[str, str]] = set()
    unique: list[ToolCall] = []
    for tc in tool_calls:
        repaired = repair_tool_name(tc.name, valid) or tc.name
        key = (repaired, tc.arguments)
        if key in seen:
            logger.warning("Removed duplicate tool call: %s", repaired)
            continue
        seen.add(key)
        if repaired != tc.name:
            logger.info("Repaired tool name %r -> %r", tc.name, repaired)
            tc = ToolCall(id=tc.id, name=repaired, arguments=tc.arguments, provider_data=tc.provider_data)
        unique.append(tc)

    delegate_count = sum(1 for tc in unique if tc.name == "delegate_task")
    if delegate_count <= MAX_CONCURRENT_DELEGATES:
        return unique

    kept = 0
    capped: list[ToolCall] = []
    for tc in unique:
        if tc.name == "delegate_task":
            if kept < MAX_CONCURRENT_DELEGATES:
                capped.append(tc)
                kept += 1
        else:
            capped.append(tc)
    logger.warning(
        "Truncated %d excess delegate_task calls (max %d)",
        delegate_count - MAX_CONCURRENT_DELEGATES,
        MAX_CONCURRENT_DELEGATES,
    )
    return capped

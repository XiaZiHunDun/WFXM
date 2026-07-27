"""Tool call deduplication utilities.

Deduplication strategy:
1. Exact match: Same tool name and arguments
2. Content hash: Hash of (name + arguments) for comparison
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToolCallKey:
    """Unique key for a tool call."""

    name: str
    args_hash: str

    @classmethod
    def from_call(cls, name: str, args: dict[str, Any]) -> "ToolCallKey":
        """Create a key from tool name and arguments."""
        args_json = json.dumps(args, sort_keys=True, default=str)
        args_hash = hashlib.md5(args_json.encode()).hexdigest()[:16]
        return cls(name=name, args_hash=args_hash)


def deduplicate_tool_calls(
    tool_calls: list[Any],
) -> tuple[list[Any], dict[str, str]]:
    """Deduplicate tool calls by name and arguments.

    Returns:
        - Deduplicated list of tool calls
        - Mapping from original call ID to deduplicated call ID
    """
    if not tool_calls:
        return [], {}

    seen: dict[ToolCallKey, Any] = {}
    result: list[Any] = []
    id_mapping: dict[str, str] = {}

    for tc in tool_calls:
        name = tc.name
        args = tc.arguments if hasattr(tc, "arguments") else {}
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                args = {}

        key = ToolCallKey.from_call(name, args)
        original_id = tc.id or f"call_{id(tc)}"

        if key in seen:
            existing = seen[key]
            id_mapping[original_id] = existing.id
        else:
            seen[key] = tc
            result.append(tc)
            id_mapping[original_id] = tc.id

    return result, id_mapping


def estimate_tool_call_overlap(
    tool_calls: list[Any],
) -> dict[str, Any]:
    """Estimate the overlap ratio in tool calls.

    Returns:
        - total: Total number of tool calls
        - unique: Number of unique tool calls
        - duplicate: Number of duplicate tool calls
        - ratio: Duplicate ratio
    """
    if not tool_calls:
        return {"total": 0, "unique": 0, "duplicate": 0, "ratio": 0.0}

    seen: set[ToolCallKey] = set()
    duplicates = 0

    for tc in tool_calls:
        name = tc.name
        args = tc.arguments if hasattr(tc, "arguments") else {}
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                args = {}

        key = ToolCallKey.from_call(name, args)
        if key in seen:
            duplicates += 1
        else:
            seen.add(key)

    total = len(tool_calls)
    unique = total - duplicates
    ratio = duplicates / total if total > 0 else 0.0

    return {
        "total": total,
        "unique": unique,
        "duplicate": duplicates,
        "ratio": round(ratio, 3),
    }


__all__ = [
    "ToolCallKey",
    "deduplicate_tool_calls",
    "estimate_tool_call_overlap",
]
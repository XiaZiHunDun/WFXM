"""Preserve recent skill read tool pairs during context compaction (DeerFlow subset)."""

from __future__ import annotations

import json
from typing import Any

from butler.env_parse import env_truthy

_SKILL_TOOLS = frozenset({"skill_view", "skills_list", "read_file"})
_SKILL_PATH_MARKERS = ("/skills/", ".butler/skills", "skills/")


def skill_compact_rescue_enabled() -> bool:
    return bool(env_truthy("BUTLER_COMPACT_SKILL_PRESERVE", default=True))


def _is_skill_tool_message(msg: dict[str, Any], id_to_name: dict[str, str]) -> bool:
    if msg.get("role") != "tool":
        return False
    tcid = str(msg.get("tool_call_id") or "")
    name = id_to_name.get(tcid, "")
    if name in ("skill_view", "skills_list"):
        return True
    if name == "read_file":
        content = str(msg.get("content") or "")
        return any(m in content for m in _SKILL_PATH_MARKERS)
    return False


def _assistant_skill_call(msg: dict[str, Any]) -> bool:
    if msg.get("role") != "assistant":
        return False
    for tc in msg.get("tool_calls") or []:
        if not isinstance(tc, dict):
            continue
        fn = tc.get("function") or {}
        name = str(fn.get("name") or "")
        if name in ("skill_view", "skills_list"):
            return True
        if name == "read_file":
            try:
                args = json.loads(str(fn.get("arguments") or "{}"))
            except json.JSONDecodeError:
                args = {}
            path = str(args.get("path") or args.get("file") or "")
            if any(m in path.replace("\\", "/") for m in _SKILL_PATH_MARKERS):
                return True
    return False


def extract_skill_rescue_messages(
    messages: list[dict[str, Any]],
    *,
    max_pairs: int = 5,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Split messages into (body_without_rescued, rescued_tail_pairs).
    Keeps up to max_pairs assistant+tool skill-related sequences from the end.
    """
    if not skill_compact_rescue_enabled() or max_pairs <= 0:
        return list(messages), []

    id_to_name: dict[str, str] = {}
    for m in messages:
        if m.get("role") != "assistant":
            continue
        for tc in m.get("tool_calls") or []:
            if not isinstance(tc, dict):
                continue
            tc_id = str(tc.get("id") or "")
            fn = tc.get("function") or {}
            if tc_id:
                id_to_name[tc_id] = str(fn.get("name") or "")

    indices: list[int] = []
    for i, m in enumerate(messages):
        if _assistant_skill_call(m):
            indices.append(i)
            for j in range(i + 1, min(i + 4, len(messages))):
                if messages[j].get("role") == "tool":
                    indices.append(j)
                    break

    if not indices:
        return list(messages), []

    keep_from = indices[-max(1, max_pairs * 2) :]
    keep_set = set(keep_from)
    # expand to full assistant+tool pairs in keep range
    start = min(keep_set)
    rescued = [dict(m) for m in messages[start:]]
    body = [dict(m) for m in messages[:start]]
    return body, rescued


def merge_skill_rescue_into_tail(
    head_tail: list[dict[str, Any]],
    rescued: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not rescued:
        return head_tail
    marker = {
        "role": "user",
        "content": "[系统提示] 以下为压缩时保留的最近 Skill 读取上下文，仅供参考。",
    }
    return head_tail + [marker] + rescued


__all__ = [
    "extract_skill_rescue_messages",
    "merge_skill_rescue_into_tail",
    "skill_compact_rescue_enabled",
]

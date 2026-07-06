"""Deterministic Todoist project-list replies (EXT-2 grounding)."""

from __future__ import annotations

import json
from typing import Any

from butler.env_parse import env_truthy
from butler.mcp.extension_grounding import matches_manifest_intent


def todoist_project_list_direct_enabled() -> bool:
    return bool(env_truthy("BUTLER_TODOIST_PROJECT_LIST_DIRECT", default=True))


def is_todoist_project_list_intent(text: str) -> bool:
    return bool(matches_manifest_intent(text, kind="project_list", server_id="todoist"))


def parse_todoist_project_list_tool_content(content: str) -> dict[str, Any] | None:
    text = str(content or "").strip()
    if not text:
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict) or payload.get("code") != "MCP_OK":
        return None
    if "project_count" not in payload and "projects" not in payload:
        return None
    if "project_count" not in payload and isinstance(payload.get("projects"), list):
        payload["project_count"] = len(payload["projects"])
    projects = payload.get("projects")
    if not str(payload.get("summary") or "").strip() and isinstance(projects, list):
        from butler.mcp.result_slim import render_todoist_project_list_summary

        payload["summary"] = render_todoist_project_list_summary(projects)
    return payload


def find_latest_todoist_project_list_envelope(messages: list[dict[str, Any]]) -> dict[str, Any] | None:
    for msg in reversed(messages):
        if not isinstance(msg, dict) or msg.get("role") != "tool":
            continue
        envelope = parse_todoist_project_list_tool_content(str(msg.get("content") or ""))
        if envelope is not None:
            return envelope
    return None


def format_todoist_project_list_reply(envelope: dict[str, Any]) -> str:
    count = int(envelope.get("project_count") or 0)
    summary = str(envelope.get("summary") or "").strip()
    if count == 0:
        return "主公，Todoist 当前没有项目（共 0 个）。"
    return f"主公，Todoist 共有 {count} 个项目：\n\n{summary}"


def try_todoist_project_list_direct_reply(
    messages: list[dict[str, Any]],
    *,
    user_text: str,
) -> str | None:
    if not todoist_project_list_direct_enabled():
        return None
    if not is_todoist_project_list_intent(user_text):
        return None
    envelope = find_latest_todoist_project_list_envelope(messages)
    if envelope is None:
        return None
    return format_todoist_project_list_reply(envelope)

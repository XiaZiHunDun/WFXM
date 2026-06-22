"""Todoist MCP project-list grounding (EXT-2)."""

from __future__ import annotations

import json

import pytest

from butler.mcp.bridge import format_call_result
from butler.mcp.todoist_grounding import (
    is_todoist_project_list_intent,
    try_todoist_project_list_direct_reply,
)


@pytest.mark.unit
def test_todoist_project_list_intent():
    assert is_todoist_project_list_intent("用 Todoist 列出所有项目")
    assert is_todoist_project_list_intent("列出待办项目")
    assert not is_todoist_project_list_intent("今天天气怎么样")


@pytest.mark.unit
def test_todoist_project_list_direct_reply():
    envelope = format_call_result(
        json.dumps(
            [
                {"id": "1", "name": "Inbox", "color": "grey"},
                {"id": "2", "name": "Work", "color": "blue"},
            ]
        ),
        tool_name="mcp_todoist_lst_projects",
        server_id="todoist",
    )
    messages = [
        {"role": "user", "content": "用 Todoist 列出所有项目"},
        {"role": "tool", "content": envelope},
    ]
    reply = try_todoist_project_list_direct_reply(
        messages,
        user_text="用 Todoist 列出所有项目",
    )
    assert reply is not None
    assert "Inbox" in reply
    assert "Work" in reply

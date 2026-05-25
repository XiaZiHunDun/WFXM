"""Agent session_todos_* tools and merge/cap helpers."""

from __future__ import annotations

import json

import pytest

from butler.core.session_todos import (
    load_session_todos,
    merge_session_todos,
    replace_session_todos,
)
from butler.tools.registry import dispatch_tool, get_tool_definitions


def test_session_todos_tools_registered():
    names = {d["function"]["name"] for d in get_tool_definitions()}
    assert "session_todos_list" in names
    assert "session_todos_write" in names


def test_session_todos_write_and_list_via_handlers(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path / "home"))
    from butler.config import reload_butler_settings
    from butler.execution_context import use_execution_context

    reload_butler_settings()

    with use_execution_context(session_key="cli:tools"):
        out = json.loads(
            dispatch_tool(
                "session_todos_write",
                {
                    "items": [
                        {"id": "a", "content": "one", "status": "pending"},
                        {"id": "b", "content": "two", "status": "in_progress"},
                    ],
                },
            )
        )
        assert out["ok"] is True
        assert out["count"] == 2

        listed = json.loads(dispatch_tool("session_todos_list", {}))
    assert listed["ok"] is True
    assert listed["open_count"] == 2
    assert len(listed["items"]) == 2


def test_session_todos_merge_by_id(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path / "home"))
    from butler.config import reload_butler_settings

    reload_butler_settings()
    replace_session_todos(
        "cli:merge",
        [{"id": "x", "content": "old", "status": "pending"}],
    )
    merge_session_todos(
        "cli:merge",
        [{"id": "x", "content": "updated", "status": "completed"}],
    )
    items = load_session_todos("cli:merge")
    assert len(items) == 1
    assert items[0]["content"] == "updated"
    assert items[0]["status"] == "completed"


def test_session_todos_write_merge_flag(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path / "home"))
    from butler.config import reload_butler_settings
    from butler.execution_context import use_execution_context

    reload_butler_settings()

    replace_session_todos(
        "cli:merge-flag",
        [{"id": "keep", "content": "stay", "status": "pending"}],
    )
    with use_execution_context(session_key="cli:merge-flag"):
        out = json.loads(
            dispatch_tool(
                "session_todos_write",
                {"items": [{"id": "keep", "status": "completed"}], "merge": True},
            )
        )
    assert out["ok"] is True
    assert out["mode"] == "merge"
    items = load_session_todos("cli:merge-flag")
    assert items[0]["status"] == "completed"
    assert "stay" in items[0]["content"]


def test_session_todos_max_items_cap(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("BUTLER_SESSION_TODOS_MAX_ITEMS", "2")
    from butler.config import reload_butler_settings

    reload_butler_settings()
    replace_session_todos(
        "cli:cap",
        [{"content": f"item-{i}"} for i in range(5)],
    )
    assert len(load_session_todos("cli:cap")) == 2


def test_format_open_todos_anchor(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path / "home"))
    from butler.config import reload_butler_settings
    from butler.core.session_todos import format_open_todos_anchor

    reload_butler_settings()
    replace_session_todos(
        "cli:anchor",
        [
            {"content": "open", "status": "pending"},
            {"content": "done", "status": "completed"},
        ],
    )
    text = format_open_todos_anchor("cli:anchor")
    assert "Session todos" in text
    assert "open" in text
    assert "done" not in text

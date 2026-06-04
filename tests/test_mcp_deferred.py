"""PR-X4: MCP deferred discovery + ask_clarification + system reminder."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from butler.core.harness_flags import (
    ask_clarification_enabled,
    mcp_deferred_tools_enabled,
    static_system_reminder_enabled,
)
from butler.core.system_reminder import maybe_prepend_system_reminder, wrap_system_reminder
from butler.core.tool_batch import ToolBatchStats, process_tool_calls
from butler.core.loop_types import LoopCallbacks, LoopConfig
from butler.mcp.deferred import (
    clear_promoted,
    get_deferred_mcp_definitions,
    get_promoted_tools,
    promote_tools,
    search_mcp_tools,
    tool_search_handler,
)
from butler.mcp.registry_hook import get_mcp_tool_definitions
from butler.transport.types import NormalizedResponse, ToolCall
from butler.tools.registry import dispatch_tool


def test_wrap_system_reminder():
    out = wrap_system_reminder("memory block")
    assert "<system-reminder>" in out
    assert "memory block" in out


def test_maybe_prepend_without_orchestrator(monkeypatch):
    monkeypatch.setenv("BUTLER_STATIC_SYSTEM_REMINDER", "1")
    assert static_system_reminder_enabled()
    assert maybe_prepend_system_reminder("user q") == "user q"


def test_mcp_deferred_promote_and_definitions(monkeypatch):
    monkeypatch.setenv("BUTLER_MCP_DEFERRED_TOOLS", "1")
    assert mcp_deferred_tools_enabled()
    clear_promoted("test-session")
    ref = MagicMock()  # noqa: magicmock-no-spec — mcp deferred facade (ref)
    ref.registered_name = "mcp_srv_tool_a"
    ref.server_id = "srv"
    ref.original_name = "tool_a"
    ref.description = "alpha tool"
    ref.classification = "read"
    ref.input_schema = {"type": "object", "properties": {}}
    with patch("butler.mcp.deferred.mcp_enabled", return_value=True):
        with patch("butler.mcp.deferred._all_mcp_refs", return_value=[ref]):
            matches = search_mcp_tools("alpha", session_key="test-session")
            assert matches
            promote_tools(["mcp_srv_tool_a"], session_key="test-session")
            assert "mcp_srv_tool_a" in get_promoted_tools("test-session")
            defs = get_deferred_mcp_definitions("test-session")
            assert defs
            assert defs[0]["function"]["name"] == "mcp_srv_tool_a"


def test_get_mcp_tool_definitions_deferred_empty_without_promote(monkeypatch):
    monkeypatch.setenv("BUTLER_MCP_DEFERRED_TOOLS", "1")
    clear_promoted("sess-b")
    with patch("butler.mcp.deferred.mcp_enabled", return_value=True):
        with patch("butler.mcp.deferred.get_deferred_mcp_definitions", return_value=[]):
            assert get_mcp_tool_definitions("sess-b") == []


def test_tool_search_handler_json():
    ref = MagicMock()  # noqa: magicmock-no-spec — mcp deferred facade (ref)
    ref.registered_name = "mcp_x_find"
    ref.server_id = "x"
    ref.original_name = "find"
    ref.description = "search things"
    ref.classification = "read"
    with patch("butler.mcp.deferred._all_mcp_refs", return_value=[ref]):
        with patch("butler.mcp.deferred.mcp_enabled", return_value=True):
            raw = tool_search_handler("search", limit=5)
    payload = json.loads(raw)
    assert payload["code"] == "MCP_TOOL_SEARCH"
    assert payload["count"] >= 1


def test_ask_clarification_dispatch(monkeypatch):
    monkeypatch.setenv("BUTLER_ASK_CLARIFICATION", "1")
    from butler.tools import registry as reg

    reg._builtins_loaded = False
    reg._ensure_builtins()
    assert ask_clarification_enabled()
    raw = dispatch_tool("ask_clarification", {"question": "选 A 还是 B?"})
    data = json.loads(raw)
    assert data.get("code") == "CLARIFICATION"
    assert "选 A" in data.get("question", "")


def test_process_tool_calls_clarification_ends_with_question():
    response = NormalizedResponse(
        tool_calls=[
            ToolCall(id="c1", name="ask_clarification", arguments='{"question":"需要哪个分支?"}'),
        ],
    )
    messages: list[dict] = []

    def _dispatch(name: str, args: dict) -> str:
        return dispatch_tool(name, args)

    stats = process_tool_calls(
        response=response,
        messages=messages,
        config=LoopConfig(),
        callbacks=LoopCallbacks(),
        guardrails=None,
        dispatch_tool=_dispatch,
        interrupt_check=lambda: False,
    )
    assert isinstance(stats, ToolBatchStats)
    assert stats.clarification_question == "需要哪个分支?"

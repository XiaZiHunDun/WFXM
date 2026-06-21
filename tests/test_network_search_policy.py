"""Network search gate: web_search-first + Firecrawl search quota."""

from __future__ import annotations

import json

import pytest

from butler.tools.network_search_policy import (
    check_network_search_tool_block,
    is_web_search_intent,
    record_network_search_tool,
    turn_network_search_scope,
)


@pytest.fixture(autouse=True)
def _enable_gate(monkeypatch):
    monkeypatch.setenv("BUTLER_NETWORK_SEARCH_GATE", "1")
    monkeypatch.setenv("BUTLER_ENABLE_WEB_SEARCH", "1")
    monkeypatch.setenv("BUTLER_FIRECRAWL_SEARCH_MAX_PER_TURN", "3")


def test_web_search_intent_detects_chinese_search():
    assert is_web_search_intent("帮我搜一下AI写作助手竞品")
    assert is_web_search_intent("竞品分析 笔灵")
    assert not is_web_search_intent("read workflow_state.json")
    assert not is_web_search_intent("用Todoist列出所有项目")


def test_todoist_query_blocks_web_search(monkeypatch):
    monkeypatch.setattr(
        "butler.tools.network_search_policy._web_search_in_current_toolset",
        lambda: True,
    )
    with turn_network_search_scope("Todoist里Inbox有哪些任务"):
        block = check_network_search_tool_block("web_search", {"query": "todoist api"})
        assert block is not None
        assert block["code"] == "TODOIST_USE_MCP"


def test_firecrawl_blocked_until_web_search(monkeypatch):
    monkeypatch.setattr(
        "butler.tools.network_search_policy._web_search_in_current_toolset",
        lambda: True,
    )
    with turn_network_search_scope("帮我搜一下竞品"):
        block = check_network_search_tool_block("mcp_firecrawl_firecrawl_search", {})
        assert block is not None
        assert block["code"] == "WEB_SEARCH_REQUIRED"

        record_network_search_tool("web_search")
        assert check_network_search_tool_block("mcp_firecrawl_firecrawl_search", {}) is None


def test_firecrawl_search_quota(monkeypatch):
    monkeypatch.setattr(
        "butler.tools.network_search_policy._web_search_in_current_toolset",
        lambda: True,
    )
    with turn_network_search_scope("帮我搜竞品"):
        record_network_search_tool("web_search")
        for _ in range(3):
            assert check_network_search_tool_block("mcp_firecrawl_firecrawl_search", {}) is None
            record_network_search_tool("mcp_firecrawl_firecrawl_search")
        block = check_network_search_tool_block("mcp_firecrawl_firecrawl_search", {})
        assert block is not None
        assert block["code"] == "FIRECRAWL_SEARCH_QUOTA"


def test_firecrawl_agent_disabled_on_search_intent(monkeypatch):
    monkeypatch.setattr(
        "butler.tools.network_search_policy._web_search_in_current_toolset",
        lambda: True,
    )
    with turn_network_search_scope("帮我搜一下竞品"):
        record_network_search_tool("web_search")
        block = check_network_search_tool_block("mcp_firecrawl_firecrawl_agent", {})
        assert block is not None
        assert block["code"] == "FIRECRAWL_AGENT_DISABLED"


def test_firecrawl_feedback_disabled_on_search_intent(monkeypatch):
    monkeypatch.setattr(
        "butler.tools.network_search_policy._web_search_in_current_toolset",
        lambda: True,
    )
    with turn_network_search_scope("帮我搜一下竞品"):
        record_network_search_tool("web_search")
        block = check_network_search_tool_block("mcp_firecrawl_firecrawl_search_feedback", {})
        assert block is not None
        assert block["code"] == "FIRECRAWL_FEEDBACK_DISABLED"


def test_search_feedback_not_counted_as_search_tool():
    from butler.tools.network_search_policy import is_firecrawl_search_tool

    assert not is_firecrawl_search_tool("mcp_firecrawl_firecrawl_search_feedback")
    assert is_firecrawl_search_tool("mcp_firecrawl_firecrawl_search")


def test_firecrawl_search_quota_via_registry(monkeypatch):
    monkeypatch.setattr(
        "butler.tools.network_search_policy._web_search_in_current_toolset",
        lambda: True,
    )
    from butler.tools import registry

    registry._REGISTRY.clear()
    registry.register(
        "web_search",
        "search",
        {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
        lambda query="", **_: json.dumps({"ok": True, "query": query}),
        toolset="network",
    )

    with turn_network_search_scope("帮我搜一下"):
        blocked = registry.dispatch_tool("mcp_firecrawl_firecrawl_search", {"query": "x"})
        payload = json.loads(blocked)
        assert payload.get("code") == "WEB_SEARCH_REQUIRED"

        registry.dispatch_tool("web_search", {"query": "x"})
        monkeypatch.setattr(
            "butler.mcp.registry_hook.is_mcp_tool",
            lambda name: name == "mcp_firecrawl_firecrawl_search",
        )
        monkeypatch.setattr(
            "butler.mcp.registry_hook.dispatch_mcp_tool",
            lambda name, args: json.dumps({"ok": True}),
        )
        ok = registry.dispatch_tool("mcp_firecrawl_firecrawl_search", {"query": "x"})
        assert '"ok": true' in ok.replace(" ", "").lower() or '"ok":true' in ok.replace(" ", "").lower()


def test_web_search_empty_exhausted(monkeypatch):
    monkeypatch.setenv("BUTLER_WEB_SEARCH_EMPTY_MAX_PER_TURN", "2")
    monkeypatch.setattr(
        "butler.tools.network_search_policy._web_search_in_current_toolset",
        lambda: True,
    )
    from butler.tools.network_search_policy import note_web_search_outcome

    with turn_network_search_scope("帮我搜一下竞品"):
        note_web_search_outcome(json.dumps({"ok": True, "results": []}))
        note_web_search_outcome(json.dumps({"ok": True, "results": []}))
        block = check_network_search_tool_block("web_search", {"query": "x"})
        assert block is not None
        assert block["code"] == "WEB_SEARCH_EXHAUSTED"

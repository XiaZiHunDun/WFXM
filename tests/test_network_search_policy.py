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


def test_dispatch_tool_applies_gate(monkeypatch):
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

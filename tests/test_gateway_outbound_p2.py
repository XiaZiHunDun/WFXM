"""MCP per-turn scrape dedup and slash single-bubble outbound prefs."""

from __future__ import annotations

import json

import pytest

from butler.gateway.outbound_prefs import (
    consume_single_bubble_reply,
    mark_slash_reply_single_bubble,
)
from butler.gateway.platforms import wechat_format as wf
from butler.mcp.registry_hook import dispatch_mcp_tool
from butler.mcp.turn_scrape_dedup import (
    check_and_record_scrape,
    is_firecrawl_scrape_tool,
    normalize_scrape_url,
    turn_scrape_dedup_scope,
)


@pytest.mark.unit
class TestSlashSingleBubble:
    def test_force_single_message_keeps_multiline_slash_reply(self):
        text = "已清空本轮对话上下文。\n长期记忆仍保留。\n（已清理 2 条会话回声）"
        chunks = wf._split_text_for_wechat_delivery(
            text, 2000, force_single_message=True,
        )
        assert chunks == [text]

    def test_outbound_prefs_one_shot(self):
        mark_slash_reply_single_bubble()
        assert consume_single_bubble_reply() is True
        assert consume_single_bubble_reply() is False


@pytest.mark.unit
class TestTurnScrapeDedup:
    def test_normalize_url_trailing_slash(self):
        a = normalize_scrape_url("https://Example.com/")
        b = normalize_scrape_url("https://example.com")
        assert a == b

    def test_duplicate_blocked_in_scope(self):
        with turn_scrape_dedup_scope():
            assert check_and_record_scrape("https://example.com") is None
            dup = check_and_record_scrape("https://example.com/")
            assert dup is not None
            assert "同一轮" in dup

    def test_firecrawl_scrape_tool_name(self):
        assert is_firecrawl_scrape_tool("mcp_firecrawl_firecrawl_scrape")
        assert not is_firecrawl_scrape_tool("mcp_firecrawl_firecrawl_map")


@pytest.mark.unit
class TestDispatchMcpScrapeDedup:
    def test_duplicate_returns_json_error(self, monkeypatch):
        monkeypatch.setenv("BUTLER_MCP_ENABLED", "1")
        with turn_scrape_dedup_scope():
            check_and_record_scrape("https://example.com")
            out = dispatch_mcp_tool(
                "mcp_firecrawl_firecrawl_scrape",
                {"url": "https://example.com/"},
            )
        assert out is not None
        data = json.loads(out)
        assert data.get("code") == "MCP_SCRAPE_DUPLICATE"

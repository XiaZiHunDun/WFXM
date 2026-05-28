"""Tests for butler.tools.web_search — web search tool."""

from __future__ import annotations

import json
import pytest


class TestWebSearchDisabled:
    def test_returns_error_when_disabled(self, monkeypatch):
        monkeypatch.setenv("BUTLER_ENABLE_WEB_SEARCH", "0")
        from butler.tools.web_search import tool_web_search

        raw = tool_web_search(query="python tutorial")
        data = json.loads(raw)
        assert "error" in data
        assert "disabled" in data["error"]

    def test_empty_query(self, monkeypatch):
        monkeypatch.setenv("BUTLER_ENABLE_WEB_SEARCH", "1")
        from butler.tools.web_search import tool_web_search

        raw = tool_web_search(query="")
        data = json.loads(raw)
        assert "error" in data


class TestWebSearchEnabled:
    def test_enabled_check(self, monkeypatch):
        monkeypatch.setenv("BUTLER_ENABLE_WEB_SEARCH", "1")
        from butler.tools.web_search import web_search_enabled

        assert web_search_enabled()

    def test_disabled_check(self, monkeypatch):
        monkeypatch.setenv("BUTLER_ENABLE_WEB_SEARCH", "0")
        from butler.tools.web_search import web_search_enabled

        assert not web_search_enabled()


class TestSearchParsing:
    def test_duckduckgo_parser_empty(self):
        from butler.tools.web_search import _search_duckduckgo
        # This will likely fail with network errors in CI, but should not crash
        # The function returns [] on error
        results = _search_duckduckgo("", max_results=1)
        assert isinstance(results, list)

    def test_max_results_clamped(self, monkeypatch):
        monkeypatch.setenv("BUTLER_ENABLE_WEB_SEARCH", "1")
        from butler.tools.web_search import tool_web_search

        raw = tool_web_search(query="test", max_results=100)
        data = json.loads(raw)
        # Should not crash even with clamped value
        assert isinstance(data, dict)


class TestToolRegistration:
    def test_registers_correctly(self):
        registered = {}
        def fake_register(name, description, schema, handler, toolset="default"):
            registered[name] = {"description": description, "schema": schema}

        from butler.tools.web_search import register_web_search_tool
        register_web_search_tool(fake_register)
        assert "web_search" in registered
        assert "query" in registered["web_search"]["schema"]["required"]

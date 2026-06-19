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


class TestSearchBudgetAndProxy:
    def test_total_budget_default(self, monkeypatch):
        monkeypatch.delenv("BUTLER_WEB_SEARCH_BUDGET", raising=False)
        from butler.tools.web_search import _total_budget

        assert _total_budget() == 60.0

    def test_total_budget_capped(self, monkeypatch):
        monkeypatch.setenv("BUTLER_WEB_SEARCH_BUDGET", "9999")
        from butler.tools.web_search import _total_budget

        assert _total_budget() == 300.0

    def test_proxy_uses_proxy_path_only_by_default(self, monkeypatch):
        monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:7890")
        monkeypatch.delenv("BUTLER_WEB_SEARCH_TRY_DIRECT", raising=False)
        from butler.tools.web_search import _search_strategies

        order = _search_strategies()
        assert order == [("html_post", True), ("html_lite", True), ("api", True)]

    def test_proxy_try_direct_restores_direct_attempts(self, monkeypatch):
        monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:7890")
        monkeypatch.setenv("BUTLER_WEB_SEARCH_TRY_DIRECT", "1")
        from butler.tools.web_search import _search_strategies

        order = _search_strategies()
        assert order[0] == ("html_post", False)
        assert ("html_post", True) in order

    def test_no_proxy_prefers_trust_env_first(self, monkeypatch):
        for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
            monkeypatch.delenv(key, raising=False)
        from butler.tools.web_search import _search_strategies

        order = _search_strategies()
        assert order[0][1] is True

    def test_search_respects_budget(self, monkeypatch):
        monkeypatch.setenv("BUTLER_WEB_SEARCH_BUDGET", "5")
        monkeypatch.setenv("BUTLER_WEB_SEARCH_RETRIES", "5")
        from butler.tools import web_search as ws

        def slow_fetch(method, url, *, trust_env, timeout, data=None):
            raise TimeoutError("slow")

        monkeypatch.setattr(ws, "_fetch_with_httpx", slow_fetch)
        started = __import__("time").monotonic()
        rows = ws._search_duckduckgo("budget test", max_results=3)
        elapsed = __import__("time").monotonic() - started
        assert rows == []
        assert elapsed < 8.0

    def test_empty_result_includes_elapsed(self, monkeypatch):
        monkeypatch.setenv("BUTLER_ENABLE_WEB_SEARCH", "1")
        from butler.tools import web_search as ws

        monkeypatch.setattr(ws, "_search_duckduckgo", lambda *_a, **_k: [])
        raw = ws.tool_web_search(query="x")
        data = json.loads(raw)
        assert "elapsed_seconds" in data
        assert data.get("budget_seconds") == 60


class TestSearchParsing:
    def test_parse_ddg_html_results(self):
        from butler.tools.web_search import parse_ddg_html_results

        html = """
        <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fa">Title A</a>
        <a class="result__snippet">Snippet A</a>
        """
        rows = parse_ddg_html_results(html, 3)
        assert len(rows) == 1
        assert rows[0]["title"] == "Title A"
        assert rows[0]["url"] == "https://example.com/a"

    def test_duckduckgo_parser_empty_query(self):
        from butler.tools.web_search import _search_duckduckgo

        results = _search_duckduckgo("", max_results=1)
        assert results == []

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

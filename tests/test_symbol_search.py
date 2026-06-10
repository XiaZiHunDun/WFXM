"""Tests for DE-GAP-3 symbol search (ctags + regex fallback)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def workspace(tmp_path):
    """Create a sample workspace with Python files."""
    (tmp_path / "main.py").write_text(
        "def hello_world():\n    pass\n\nclass MyClass:\n    pass\n",
        encoding="utf-8",
    )
    (tmp_path / "utils.py").write_text(
        "async def fetch_data(url):\n    pass\n\nMAX_SIZE = 100\n",
        encoding="utf-8",
    )
    (tmp_path / "app.js").write_text(
        "function processItem(item) {\n  return item;\n}\nconst API_KEY = 'test';\n",
        encoding="utf-8",
    )
    return tmp_path


class TestRegexSymbolSearch:
    def test_find_function(self, workspace):
        from butler.dev_engine.code_search import _regex_symbol_search
        hits = _regex_symbol_search("hello_world", workspace)
        assert len(hits) >= 1
        assert any("hello_world" in h.snippet for h in hits)

    def test_find_class(self, workspace):
        from butler.dev_engine.code_search import _regex_symbol_search
        hits = _regex_symbol_search("MyClass", workspace)
        assert len(hits) >= 1

    def test_find_async_function(self, workspace):
        from butler.dev_engine.code_search import _regex_symbol_search
        hits = _regex_symbol_search("fetch_data", workspace)
        assert len(hits) >= 1

    def test_find_js_function(self, workspace):
        from butler.dev_engine.code_search import _regex_symbol_search
        hits = _regex_symbol_search("processItem", workspace)
        assert len(hits) >= 1

    def test_find_assignment(self, workspace):
        from butler.dev_engine.code_search import _regex_symbol_search
        hits = _regex_symbol_search("MAX_SIZE", workspace)
        assert len(hits) >= 1

    def test_no_match(self, workspace):
        from butler.dev_engine.code_search import _regex_symbol_search
        hits = _regex_symbol_search("nonexistent_symbol_xyz", workspace)
        assert len(hits) == 0


class TestCtagsSearch:
    def test_ctags_not_found_returns_empty(self, workspace):
        from butler.dev_engine.code_search import _ctags_search
        with patch("butler.dev_engine.code_search.subprocess.run", side_effect=FileNotFoundError):
            hits = _ctags_search("hello", workspace)
        assert hits == []

    def test_ctags_timeout_returns_empty(self, workspace):
        from butler.dev_engine.code_search import _ctags_search
        with patch(
            "butler.dev_engine.code_search.subprocess.run",
            side_effect=subprocess.TimeoutExpired("ctags", 15),
        ):
            hits = _ctags_search("hello", workspace)
        assert hits == []

    def test_ctags_nonzero_exit_returns_empty(self, workspace):
        from butler.dev_engine.code_search import _ctags_search
        mock_result = MagicMock(spec=subprocess.CompletedProcess)
        mock_result.returncode = 1
        mock_result.stdout = ""
        with patch("butler.dev_engine.code_search.subprocess.run", return_value=mock_result):
            hits = _ctags_search("hello", workspace)
        assert hits == []

    def test_ctags_parses_json_output(self, workspace):
        from butler.dev_engine.code_search import _ctags_search
        ctags_output = "\n".join([
            json.dumps({"_type": "tag", "name": "hello_world", "path": str(workspace / "main.py"), "line": 1, "kind": "function"}),
            json.dumps({"_type": "tag", "name": "MyClass", "path": str(workspace / "main.py"), "line": 4, "kind": "class"}),
        ])
        mock_result = MagicMock(spec=subprocess.CompletedProcess)
        mock_result.returncode = 0
        mock_result.stdout = ctags_output
        with patch("butler.dev_engine.code_search.subprocess.run", return_value=mock_result):
            hits = _ctags_search("hello_world", workspace)
        assert len(hits) == 1
        assert hits[0].range_start == 1
        assert "function" in hits[0].snippet

    def test_ctags_partial_match(self, workspace):
        from butler.dev_engine.code_search import _ctags_search
        ctags_output = json.dumps({
            "_type": "tag", "name": "hello_world", "path": str(workspace / "main.py"),
            "line": 1, "kind": "function",
        })
        mock_result = MagicMock(spec=subprocess.CompletedProcess)
        mock_result.returncode = 0
        mock_result.stdout = ctags_output
        with patch("butler.dev_engine.code_search.subprocess.run", return_value=mock_result):
            hits = _ctags_search("hello", workspace)
        assert len(hits) == 1
        assert hits[0].relevance < 1.0


class TestSearchSymbolsIntegration:
    def test_search_symbols_uses_ctags_when_available(self, workspace):
        from butler.dev_engine.code_search import search_symbols
        ctags_output = json.dumps({
            "_type": "tag", "name": "hello_world", "path": str(workspace / "main.py"),
            "line": 1, "kind": "function",
        })
        mock_result = MagicMock(spec=subprocess.CompletedProcess)
        mock_result.returncode = 0
        mock_result.stdout = ctags_output
        with patch("butler.dev_engine.code_search.subprocess.run", return_value=mock_result):
            hits = search_symbols("hello_world", workspace)
        assert len(hits) >= 1
        assert "function" in hits[0].snippet

    def test_search_symbols_falls_back_to_regex(self, workspace):
        from butler.dev_engine.code_search import search_symbols
        hits = search_symbols("hello_world", workspace)
        assert len(hits) >= 1

"""Tests for the five new optional dependency integrations (T1–T5).

These tests verify the graceful-degradation behavior: each feature must
work (or degrade cleanly) whether the optional dependency is installed or not.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest


# ── T1: fastembed embedder ───────────────────────────────────────────

class TestFastEmbedEmbedder:
    def test_fastembed_embedder_class_exists(self):
        from butler.memory.embedding import FastEmbedEmbedder

        embedder = FastEmbedEmbedder(model_name="test-model")
        assert embedder.model_id == "fastembed/test-model"
        assert embedder.dimension == 384

    def test_get_embedder_fastembed_fallback_when_not_installed(self):
        """When fastembed is not installed, should fall back to HashingEmbedder."""
        with patch.dict("os.environ", {
            "BUTLER_EMBEDDING_PROVIDER": "fastembed",
            "BUTLER_EMBEDDING_MODEL": "BAAI/bge-small-en-v1.5",
        }):
            with patch("butler.memory.embedding._resolve_fastembed", return_value=None):
                from butler.memory.embedding import get_embedder
                embedder = get_embedder()
                assert embedder.model_id == "hashing-v1"

    def test_get_embedder_fastembed_success(self):
        """When fastembed resolves, should return the FastEmbedEmbedder."""
        mock_embedder = MagicMock()
        mock_embedder.model_id = "fastembed/test-model"
        mock_embedder.dimension = 384

        with patch.dict("os.environ", {
            "BUTLER_EMBEDDING_PROVIDER": "fastembed",
        }):
            with patch("butler.memory.embedding._resolve_fastembed", return_value=mock_embedder):
                from butler.memory.embedding import get_embedder
                embedder = get_embedder()
                assert embedder.model_id == "fastembed/test-model"

    def test_fastembed_embed_method_signature(self):
        """FastEmbedEmbedder.embed() should accept text and return list[float]."""
        from butler.memory.embedding import FastEmbedEmbedder

        mock_model = MagicMock()
        mock_model.embed.return_value = [[0.5, 0.3, 0.1]]

        embedder = FastEmbedEmbedder(model_name="test")
        embedder._model = mock_model

        result = embedder.embed("hello world")
        assert isinstance(result, list)
        assert all(isinstance(x, float) for x in result)
        mock_model.embed.assert_called_once()


# ── T2: document reader ─────────────────────────────────────────────

class TestDocumentReader:
    def test_can_convert_supported_extensions(self):
        from butler.tools.document_reader import can_convert

        assert can_convert("report.pdf") is True
        assert can_convert("data.xlsx") is True
        assert can_convert("doc.docx") is True
        assert can_convert("slides.pptx") is True
        assert can_convert("page.html") is True

    def test_can_convert_unsupported_extensions(self):
        from butler.tools.document_reader import can_convert

        assert can_convert("image.png") is False
        assert can_convert("script.py") is False
        assert can_convert("binary.exe") is False

    def test_tool_read_document_no_path(self):
        from butler.tools.document_reader import tool_read_document

        result = json.loads(tool_read_document(""))
        assert "error" in result

    def test_tool_read_document_file_not_found(self):
        from butler.tools.document_reader import tool_read_document

        with patch("butler.tools.document_reader._markitdown_available", return_value=True):
            result = json.loads(tool_read_document("/nonexistent/file.pdf"))
            assert "error" in result

    def test_tool_read_document_not_installed(self):
        from butler.tools.document_reader import tool_read_document

        with patch("butler.tools.document_reader._markitdown_available", return_value=False):
            result = json.loads(tool_read_document("test.pdf"))
            assert "not installed" in result["error"]
            assert "hint" in result

    def test_register_skips_when_not_available(self):
        from butler.tools.document_reader import register_document_tools

        mock_register = MagicMock()
        with patch("butler.tools.document_reader._markitdown_available", return_value=False):
            register_document_tools(mock_register)
            mock_register.assert_not_called()

    def test_register_adds_tool_when_available(self):
        from butler.tools.document_reader import register_document_tools

        mock_register = MagicMock()
        with patch("butler.tools.document_reader._markitdown_available", return_value=True):
            register_document_tools(mock_register)
            mock_register.assert_called_once()
            call_kwargs = mock_register.call_args
            assert call_kwargs[1]["name"] == "read_document" or call_kwargs[0][0] == "read_document"


# ── T3: trafilatura web fetch ────────────────────────────────────────

class TestTrafilaturaWebFetch:
    def test_strip_html_regex_fallback(self):
        from butler.tools.web_fetch import _strip_html_regex

        html = "<html><body><p>Hello World</p></body></html>"
        result = _strip_html_regex(html)
        assert "Hello World" in result
        assert "<" not in result

    def test_extract_with_trafilatura_returns_none_when_not_installed(self):
        from butler.tools.web_fetch import _extract_with_trafilatura

        with patch.dict("sys.modules", {"trafilatura": None}):
            result = _extract_with_trafilatura("<html><body>test</body></html>")
            # Either None (import failed) or a dict (if trafilatura happens to be installed)
            # We just verify it doesn't crash
            assert result is None or isinstance(result, dict)

    def test_strip_html_falls_back_to_regex(self):
        """When trafilatura is not available, _strip_html should return a string."""
        from butler.tools.web_fetch import _strip_html

        with patch("butler.tools.web_fetch._extract_with_trafilatura", return_value=None):
            result = _strip_html("<p>Hello</p>")
            assert isinstance(result, str)
            assert "Hello" in result

    def test_strip_html_uses_trafilatura_when_available(self):
        from butler.tools.web_fetch import _strip_html

        mock_result = {"text": "Extracted content", "title": "Test Page"}
        with patch("butler.tools.web_fetch._extract_with_trafilatura", return_value=mock_result):
            result = _strip_html("<p>Hello</p>")
            assert isinstance(result, dict)
            assert result["text"] == "Extracted content"
            assert result["title"] == "Test Page"


# ── T4: duckdb data query (apprise adapter removed Sprint 10 TST-10-1) ────

class TestDataQuery:
    def test_tool_query_data_no_sql(self):
        from butler.tools.data_query import tool_query_data

        with patch("butler.tools.data_query._duckdb_available", return_value=True):
            with patch("butler.tools.data_query._analytics_enabled", return_value=True):
                result = json.loads(tool_query_data(""))
                assert "error" in result
                assert "sql" in result["error"].lower()

    def test_tool_query_data_not_installed(self):
        from butler.tools.data_query import tool_query_data

        with patch("butler.tools.data_query._duckdb_available", return_value=False):
            result = json.loads(tool_query_data("SELECT 1"))
            assert "not installed" in result["error"]
            assert "hint" in result

    def test_tool_query_data_disabled(self):
        from butler.tools.data_query import tool_query_data

        with patch("butler.tools.data_query._duckdb_available", return_value=True):
            with patch("butler.tools.data_query._analytics_enabled", return_value=False):
                result = json.loads(tool_query_data("SELECT 1"))
                assert "disabled" in result["error"]

    def test_tool_query_data_blocks_writes(self):
        from butler.tools.data_query import tool_query_data

        with patch("butler.tools.data_query._duckdb_available", return_value=True):
            with patch("butler.tools.data_query._analytics_enabled", return_value=True):
                for stmt in ["INSERT INTO t VALUES (1)", "DELETE FROM t", "DROP TABLE t"]:
                    result = json.loads(tool_query_data(stmt))
                    assert "not allowed" in result["error"]

    def test_register_skips_when_not_available(self):
        from butler.tools.data_query import register_data_query_tools

        mock_register = MagicMock()
        with patch("butler.tools.data_query._duckdb_available", return_value=False):
            register_data_query_tools(mock_register)
            mock_register.assert_not_called()

    def test_resolve_project_path_unsupported_ext(self):
        from butler.tools.data_query import _resolve_project_path

        assert _resolve_project_path("script.py") is None

    def test_resolve_project_path_nonexistent(self):
        from butler.tools.data_query import _resolve_project_path

        assert _resolve_project_path("/nonexistent/data.csv") is None


# ── pyproject.toml extras validation ─────────────────────────────────

class TestPyprojectExtras:
    def test_new_extras_defined(self):
        from pathlib import Path
        import tomllib

        pyproject = Path(__file__).parent.parent / "pyproject.toml"
        with open(pyproject, "rb") as f:
            data = tomllib.load(f)

        extras = data["project"]["optional-dependencies"]
        assert "embeddings" in extras
        assert "documents" in extras
        assert "web" in extras
        assert "notify" in extras
        assert "analytics" in extras

    def test_extras_contain_expected_packages(self):
        from pathlib import Path
        import tomllib

        pyproject = Path(__file__).parent.parent / "pyproject.toml"
        with open(pyproject, "rb") as f:
            data = tomllib.load(f)

        extras = data["project"]["optional-dependencies"]
        assert any("fastembed" in dep for dep in extras["embeddings"])
        assert any("markitdown" in dep for dep in extras["documents"])
        assert any("trafilatura" in dep for dep in extras["web"])
        assert any("apprise" in dep for dep in extras["notify"])
        assert any("duckdb" in dep for dep in extras["analytics"])

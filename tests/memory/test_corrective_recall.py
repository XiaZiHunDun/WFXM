"""R6-1: unit tests for butler.memory.corrective_recall."""

from __future__ import annotations

import json

import pytest

from butler.config import reload_butler_settings
from butler.memory.corrective_recall import (
    build_corrective_recall_block,
    corrective_recall_enabled,
    extract_query_from_task,
    should_trigger_corrective,
)


@pytest.fixture
def butler_home(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    reload_butler_settings()
    yield tmp_path
    reload_butler_settings()


@pytest.mark.unit
class TestCorrectiveRecallEnabled:
    def test_enabled_by_default(self, butler_home):
        assert corrective_recall_enabled() is True

    def test_disabled_via_env(self, butler_home, monkeypatch):
        monkeypatch.setenv("BUTLER_CORRECTIVE_RECALL", "0")
        reload_butler_settings()
        assert corrective_recall_enabled() is False


@pytest.mark.unit
class TestShouldTriggerCorrective:
    def test_skips_when_disabled(self, butler_home, monkeypatch):
        monkeypatch.setenv("BUTLER_CORRECTIVE_RECALL", "0")
        reload_butler_settings()
        assert should_trigger_corrective("read_file", "error: not found") is False

    def test_skips_recall_tools(self, butler_home):
        assert should_trigger_corrective("butler_recall", "error failed") is False
        assert should_trigger_corrective("search_project_knowledge", "timeout") is False

    def test_skips_short_body(self, butler_home):
        assert should_trigger_corrective("read_file", "err") is False

    def test_triggers_on_json_error(self, butler_home):
        body = '{"error": "permission denied"}'
        assert should_trigger_corrective("read_file", body) is True

    def test_triggers_on_failure_hint(self, butler_home):
        assert should_trigger_corrective("terminal", "command failed with exit 1") is True


@pytest.mark.unit
class TestExtractQueryFromTask:
    def test_collapses_whitespace_and_truncates(self):
        raw = "  fix   deploy   " + ("x" * 300)
        q = extract_query_from_task(raw, max_len=50)
        assert len(q) == 50
        assert "fix deploy" in q

    def test_empty_task_returns_empty(self):
        assert extract_query_from_task("") == ""


@pytest.mark.unit
class TestBuildCorrectiveRecallBlock:
    def test_returns_empty_without_query(self, butler_home):
        assert build_corrective_recall_block(
            task="",
            tool_name="read_file",
            error_excerpt="",
        ) == ""

    def test_builds_markdown_from_recall_results(self, butler_home, monkeypatch):
        def fake_recall(**_kwargs):
            return json.dumps({"results": [{"content": "prior fix for deploy"}]})

        monkeypatch.setattr(
            "butler.tools.memory_tools.tool_butler_recall",
            fake_recall,
        )
        block = build_corrective_recall_block(
            task="fix deploy pipeline",
            tool_name="terminal",
            error_excerpt="error: command failed",
            scope="project",
        )
        assert "## Corrective recall" in block
        assert "terminal" in block
        assert "prior fix for deploy" in block

    def test_swallows_recall_errors(self, butler_home, monkeypatch):
        def boom(**_kwargs):
            raise RuntimeError("recall down")

        monkeypatch.setattr(
            "butler.tools.memory_tools.tool_butler_recall",
            boom,
        )
        assert build_corrective_recall_block(
            task="deploy",
            tool_name="read_file",
            error_excerpt="failed",
        ) == ""

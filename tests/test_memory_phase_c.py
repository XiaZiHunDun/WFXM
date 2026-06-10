"""Memory phase C: unified IndexSync and semantic index drift detection."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from butler.memory.butler_memory import ButlerMemory
from butler.memory.semantic_health import (
    drift_from_butler_memory,
    experience_vector_drift,
)
from butler.session.lifecycle import CONVERSATION_CATEGORY


class TestExperienceVectorDrift:
    def test_stale_when_large_gap(self):
        drift = experience_vector_drift(experience_long_term=20, experience_vectors=5)
        assert drift["semantic_index_stale"] is True
        assert drift["semantic_index_gap"] == 15

    def test_ok_when_fully_synced(self):
        drift = experience_vector_drift(experience_long_term=10, experience_vectors=10)
        assert drift["semantic_index_stale"] is False
        assert drift["semantic_index_gap"] == 0

    def test_small_gap_not_stale(self):
        drift = experience_vector_drift(experience_long_term=10, experience_vectors=9)
        assert drift["semantic_index_stale"] is False


class TestButlerMemoryAddExperience:
    def test_add_experience_indexes_non_conversation(self, monkeypatch):
        monkeypatch.setenv("BUTLER_SEMANTIC_MEMORY", "1")
        with tempfile.TemporaryDirectory() as td:
            bm = ButlerMemory(Path(td))
            assert bm.semantic is not None
            row_id = bm.add_experience("p", "note", "phase-c index sync marker")
            assert row_id > 0
            from butler.memory.semantic_index import SOURCE_EXPERIENCE

            assert bm.semantic.count_by_source(SOURCE_EXPERIENCE) >= 1
            bm.close()

    def test_add_experience_skips_conversation_vectors(self, monkeypatch):
        monkeypatch.setenv("BUTLER_SEMANTIC_MEMORY", "1")
        with tempfile.TemporaryDirectory() as td:
            bm = ButlerMemory(Path(td))
            from butler.memory.semantic_index import SOURCE_EXPERIENCE

            before = bm.semantic.count_by_source(SOURCE_EXPERIENCE)
            row_id = bm.add_experience(
                "",
                CONVERSATION_CATEGORY,
                "Q: hi → A: hello",
                tags="session:test",
            )
            assert row_id > 0
            assert bm.semantic.count_by_source(SOURCE_EXPERIENCE) == before
            bm.close()


class TestDriftFromButlerMemory:
    def test_drift_reports_stale_after_unindexed_add(self, monkeypatch):
        monkeypatch.setenv("BUTLER_SEMANTIC_MEMORY", "1")
        with tempfile.TemporaryDirectory() as td:
            bm = ButlerMemory(Path(td))
            bm.experience.add("p", "note", "unindexed row one")
            bm.experience.add("p", "note", "unindexed row two")
            bm.experience.add("p", "note", "unindexed row three")
            drift = drift_from_butler_memory(bm)
            assert drift["experience_indexable"] == 3
            assert drift["experience_vectors"] == 0
            assert drift["semantic_index_stale"] is True
            bm.close()


class TestDiagnosticsStaleLine:
    def test_format_includes_stale_warning(self):
        from butler.memory.diagnostics import format_memory_diagnostic_lines

        lines = format_memory_diagnostic_lines(
            {
                "semantic_enabled": True,
                "vector_rows": 50,
                "vector_model": "test-model",
                "experience_long_term": 10,
                "conversation_rows": 0,
                "profile_entries": 0,
                "profile_chars": 0,
                "project_bullets": 0,
                "project_pending": 0,
                "experience_indexable": 10,
                "experience_vectors": 2,
                "semantic_index_stale": True,
                "semantic_index_gap": 8,
            }
        )
        sync_lines = [ln for ln in lines if "向量同步" in ln]
        assert sync_lines
        assert "reindex" in sync_lines[0]

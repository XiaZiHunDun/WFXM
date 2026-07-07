"""Phase 1 observability wiring — L2 metrics + embedding health."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from butler.core.fact_extraction import extract_pre_compact_facts
from butler.memory.memory_metrics import MemoryMetricsCollector, get_collector
from butler.session.memory_prefetch_ops import emit_prefetch_metrics, prefetch_retrieval_counts


class TestPrefetchRetrievalWiring:
    def setup_method(self):
        MemoryMetricsCollector.reset()

    def test_retrieval_counts_from_diagnostics(self):
        diag = {
            "memory_experience_hits": 3,
            "memory_profile_vector_hits": 1,
            "memory_butler_context": True,
            "memory_facts_chars": 120,
        }
        total, relevant = prefetch_retrieval_counts(diag)
        assert total == 6
        assert relevant == 6

    def test_emit_prefetch_metrics_calls_on_retrieval(self):
        get_collector().start_session("sess-1")
        diag = {"memory_experience_hits": 2, "memory_project_query_hits": 1}
        emit_prefetch_metrics("test query", hit=True, result_count=2, diagnostics=diag)
        m = get_collector()._current()
        assert m is not None
        assert m.prefetch_turns == 1
        assert m.retrieval_total == 3
        assert m.retrieval_relevant == 3


class TestFactExtractionMetricsWiring:
    def setup_method(self):
        MemoryMetricsCollector.reset()

    def test_extract_emits_fact_metrics(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BUTLER_FACT_EXTRACTION", "1")
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
        get_collector().start_session("fact-sess")
        messages = [
            {
                "role": "assistant",
                "content": "已决定使用 pytest 作为测试框架",
            }
        ]
        extract_pre_compact_facts("fact-sess", messages)
        m = get_collector()._current()
        assert m is not None
        assert m.facts_pre_compact >= 0
        assert m.facts_post_compact >= m.facts_pre_compact


class TestEmbeddingHealth:
    def test_check_embedding_recall_runs(self):
        from butler.ops.embedding_health import check_embedding_recall

        report = check_embedding_recall(min_recall=0.0)
        assert report.total == 5
        assert 0.0 <= report.recall_at_3 <= 1.0
        assert report.message

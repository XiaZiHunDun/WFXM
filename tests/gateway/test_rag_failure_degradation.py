"""AP-3: RAG / embedding failure must degrade visibly without fabricated hits."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from butler.execution_context import use_execution_context
from butler.memory.retrieval_telemetry import clear_last_retrieval, get_last_retrieval
from butler.memory.semantic_index import hybrid_experience_search


@pytest.mark.unit
class TestRagFailureDegradation:
    def test_hybrid_search_500_sets_recall_degraded_telemetry(self):
        session_key = "ap3-rag-500"
        clear_last_retrieval(session_key)
        sem = MagicMock()
        sem.hybrid_search.side_effect = RuntimeError("upstream 500")

        fts = MagicMock(return_value=[{"id": "1", "content": "fts-only", "score": 0.4}])

        with use_execution_context(MagicMock(), session_key=session_key):
            hits = hybrid_experience_search(sem, fts, "sales report", project="demo")

        assert hits  # FTS fallback still returns hits
        tel = get_last_retrieval(session_key)
        assert tel.get("recall_degraded") is True
        assert "fts-error-fallback" in str(tel.get("mode") or "")

    def test_degraded_hits_not_marked_as_semantic_truth(self):
        """Fallback FTS rows must not pretend to be high-confidence semantic matches."""
        session_key = "ap3-no-fabricate"
        clear_last_retrieval(session_key)
        sem = MagicMock()
        sem.hybrid_search.side_effect = ConnectionError("API 500")

        fts = MagicMock(
            return_value=[
                {
                    "id": "1",
                    "content": "synthetic-fts-only",
                    "score": 0.1,
                    "source": "experience",
                }
            ]
        )

        with use_execution_context(MagicMock(), session_key=session_key):
            hits = hybrid_experience_search(sem, fts, "query", project=None)

        assert hits[0]["content"] == "synthetic-fts-only"
        assert get_last_retrieval(session_key).get("recall_degraded") is True
        # No fake "semantic_score" injected by fallback path
        assert "semantic_score" not in hits[0]

    def test_rag_diagnostics_surfaces_degraded_recall(self):
        from butler.ops.rag_diagnostics import format_rag_diagnostic_lines

        session_key = "ap3-diag"
        clear_last_retrieval(session_key)
        with use_execution_context(MagicMock(), session_key=session_key):
            from butler.memory.retrieval_telemetry import record_last_retrieval

            record_last_retrieval(
                session_key,
                {
                    "mode": "fts-error-fallback",
                    "fallbacks": 1,
                    "candidates": 1,
                    "query": "q",
                    "recall_degraded": True,
                },
            )
            lines = format_rag_diagnostic_lines(session_key=session_key)
        text = "\n".join(lines)
        assert "降级" in text or "degraded" in text.lower() or "FTS" in text


@pytest.mark.integration
def test_memory_prefetch_on_hybrid_failure_records_degraded(tmp_path, monkeypatch):
    """End-to-end: prefetch path records degraded telemetry on hybrid failure."""
    from butler.memory import semantic_index as si_mod
    from butler.memory.retrieval_telemetry import record_last_retrieval

    session_key = "wechat:ap3-prefetch"
    clear_last_retrieval(session_key)

    def _boom(*_a, **_k):
        raise RuntimeError("vector API 500")

    orch = MagicMock()
    orch.project_manager.get_current.return_value = MagicMock(
        name="demo",
        workspace=tmp_path,
    )

    sem = MagicMock()
    sem.hybrid_search.side_effect = RuntimeError("vector API 500")
    fts = MagicMock(
        return_value=[
            {"id": 1, "content": "fts", "score": 0.5, "source": "experience"},
        ]
    )

    with use_execution_context(orch, session_key=session_key):
        si_mod.hybrid_experience_search(sem, fts, "task", project="demo")

    tel = get_last_retrieval(session_key)
    assert tel.get("recall_degraded") is True

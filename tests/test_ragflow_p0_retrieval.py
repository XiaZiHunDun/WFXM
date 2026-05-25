"""RAGFlow P0: retrieval fallback and diagnostics enrichment."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from butler.memory.semantic_index import hybrid_experience_search
from butler.memory.diagnostics import collect_memory_layer_stats
from butler.ops.rag_diagnostics import format_rag_diagnostic_lines


@pytest.mark.module_test
def test_hybrid_experience_search_falls_back_without_project_filter():
    calls: list[tuple[str | None, int]] = []

    def _fts_search(query: str, project: str | None = None, limit: int = 10):
        del query
        calls.append((project, limit))
        if project == "demo":
            return []
        return [
            {
                "id": 7,
                "project": "other",
                "category": "experience",
                "content": "跨项目检索命中了 pytest 守门经验",
                "score": 0.9,
            }
        ]

    out = hybrid_experience_search(
        None,
        _fts_search,
        "pytest 守门",
        project="demo",
        limit=3,
    )

    assert out
    assert "pytest" in out[0]["content"]
    assert calls == [("demo", 6), (None, 12)]


@pytest.mark.module_test
def test_format_rag_diagnostic_lines_shows_last_retrieval_details():
    lines = format_rag_diagnostic_lines(
        {
            "semantic_enabled": True,
            "vector_rows": 12,
            "vector_model": "hashing",
            "rag_last_mode": "fts-fallback-global",
            "rag_last_fallbacks": 1,
            "rag_last_candidates": 6,
            "rag_last_query": "pytest 守门",
        }
    )

    assert any("最近检索模式" in ln and "fts-fallback-global" in ln for ln in lines)
    assert any("最近 fallback" in ln and "1" in ln for ln in lines)
    assert any("最近候选数" in ln and "6" in ln for ln in lines)
    assert any("最近检索词" in ln and "pytest 守门" in ln for ln in lines)
    assert any("混合权重" in ln for ln in lines)


@pytest.mark.module_test
def test_collect_memory_layer_stats_merges_last_retrieval():
    from butler.memory.retrieval_telemetry import record_last_retrieval

    orch = MagicMock()
    orch.butler_memory = None
    orch._project_memory = None
    orch.project_manager.get_current.return_value = None

    record_last_retrieval(
        "s-rag",
        {
            "mode": "fts-fallback-global",
            "fallbacks": 1,
            "candidates": 6,
            "query": "pytest 守门",
        },
    )
    stats = collect_memory_layer_stats(orch, session_key="s-rag")

    assert stats["rag_last_mode"] == "fts-fallback-global"
    assert stats["rag_last_fallbacks"] == 1
    assert stats["rag_last_candidates"] == 6


@pytest.mark.module_test
def test_clear_session_boundary_memory_clears_last_retrieval():
    from butler.memory.retrieval_telemetry import get_last_retrieval, record_last_retrieval
    from butler.session_lifecycle import clear_session_boundary_memory

    orch = MagicMock()
    orch.butler_memory = None
    orch.memory_provider = None
    orch._memory_provider = None

    record_last_retrieval(
        "s-clear",
        {"mode": "hybrid", "fallbacks": 0, "candidates": 2, "query": "pytest"},
    )
    assert get_last_retrieval("s-clear")

    clear_session_boundary_memory(orch, "s-clear")
    assert get_last_retrieval("s-clear") == {}


@pytest.mark.module_test
def test_prefetch_turn_memory_records_project_retrieval_mode(tmp_path, monkeypatch):
    from butler.execution_context import use_execution_context
    from butler.memory.project_memory import ProjectMemory
    from butler.session_lifecycle import prefetch_turn_memory

    monkeypatch.setenv("BUTLER_SEMANTIC_MEMORY", "0")
    (tmp_path / "project.yaml").write_text("name: demo\nworkspace: .\n", encoding="utf-8")
    pm = ProjectMemory(tmp_path)
    pm.markdown.append("Notes", "守门测试用 pytest", classification="fact")

    orch = MagicMock()
    orch.butler_memory = None
    orch._project_memory = pm
    proj = MagicMock()
    proj.name = "demo"
    proj.workspace = tmp_path
    orch.project_manager.get_current.return_value = proj
    orch.project_manager.current_project = "demo"
    orch.project_manager.resolve_active_project_name.return_value = "demo"

    with use_execution_context(orch, session_key="s-project"):
        text = prefetch_turn_memory(orch, "pytest", role="butler", use_cache=False)

    stats = collect_memory_layer_stats(orch, session_key="s-project")
    assert "pytest" in text.lower()
    assert stats["rag_last_mode"] == "project-keyword"
    assert stats["rag_last_fallbacks"] == 0

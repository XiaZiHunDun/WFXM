"""CLI memory search and structured knowledge_search enrichment."""

from __future__ import annotations

import json

import pytest


@pytest.mark.module_test
def test_format_rag_diagnostic_lines_includes_hybrid_weights():
    from butler.ops.rag_diagnostics import format_rag_diagnostic_lines

    lines = format_rag_diagnostic_lines({"semantic_enabled": False})
    assert any("混合权重" in ln for ln in lines)


@pytest.mark.module_test
def test_enrich_search_hit_adds_structured_fields():
    from butler.memory.search_result import enrich_search_hit

    hit = enrich_search_hit(
        {
            "source": "experience",
            "source_id": "42",
            "content": "pytest 结构化字段",
            "score": 0.88,
            "retrieval": "hybrid-vector",
        }
    )
    assert hit["chunk_id"] == "experience:42"
    assert "experience.db" in hit["source_path"]
    assert hit["score_breakdown"]["final_score"] == 0.88
    assert "hybrid_vector_weight" in hit["score_breakdown"]


@pytest.mark.module_test
def test_tool_search_project_knowledge_enriches_json(monkeypatch):
    from butler.tools import knowledge_search
    payload = {
        "ok": True,
        "scope": "project",
        "project": "demo",
        "results": [{"content": "决策记录", "score": 0.5}],
    }
    monkeypatch.setattr(
        "butler.tools.memory_tools.tool_butler_recall",
        lambda **_: json.dumps(payload, ensure_ascii=False),
    )
    monkeypatch.setattr(
        "butler.memory.corpus_router.corpus_routing_enabled",
        lambda: False,
    )

    out = knowledge_search.tool_search_project_knowledge(query="决策", limit=3)
    data = json.loads(out)
    assert data["results"][0]["chunk_id"]
    assert data["results"][0]["score_breakdown"]


@pytest.mark.module_test
def test_run_memory_search_experience_fts(tmp_path, monkeypatch):
    from butler.memory.butler_memory import ButlerMemory
    from butler.memory.search_cli import run_memory_search

    monkeypatch.setenv("BUTLER_SEMANTIC_MEMORY", "0")
    home = tmp_path / "butler_home"
    home.mkdir()
    bm = ButlerMemory(home, tenant_id="default")
    bm.experience.add("demo", "experience", "守门经验 pytest CLI")

    payload = run_memory_search(
        home,
        "pytest CLI",
        scope="experience",
        limit=5,
        verbose=False,
        json_out=True,
    )
    assert payload.get("ok")
    assert payload.get("results")
    assert payload.get("mode")

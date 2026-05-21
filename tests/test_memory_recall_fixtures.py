"""Paraphrase recall regression fixtures (vector + keyword)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from butler.memory import ButlerMemory
from butler.memory.embedding import HashingEmbedder
from butler.memory.project_memory import ProjectMemory
from butler.memory.semantic_index import SemanticMemoryIndex
from butler.memory.semantic_project import (
    index_project_memory_bullet,
    prefetch_project_memory_hits,
    search_project_memory_keywords,
)

_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "memory_recall" / "cases.json"


def _load_cases() -> list[dict]:
    return json.loads(_FIXTURES.read_text(encoding="utf-8"))


@pytest.mark.module_test
class TestMemoryRecallFixtures:
    @pytest.fixture
    def indexed_project(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BUTLER_SEMANTIC_MEMORY", "1")
        proj_dir = tmp_path / "fixture"
        proj_dir.mkdir()
        (proj_dir / "project.yaml").write_text(
            f"name: recall-fixture\nworkspace: {proj_dir}\n",
            encoding="utf-8",
        )
        bm = ButlerMemory(tmp_path / "home", tenant_id="default")
        pm = ProjectMemory(proj_dir)
        sem = bm.semantic
        assert sem is not None
        for case in _load_cases():
            pm.markdown.append(
                case["section"],
                case["stored"],
                classification="fact",
            )
            index_project_memory_bullet(
                sem,
                case["project"],
                case["section"],
                case["stored"],
            )
        return bm, pm, sem

    @pytest.mark.parametrize("case", _load_cases(), ids=[c["id"] for c in _load_cases()])
    def test_vector_paraphrase_recall(self, indexed_project, case):
        if case.get("keyword_only"):
            pytest.skip("keyword-only case")
        bm, pm, sem = indexed_project
        stored = case["stored"]
        for query in case["queries"]:
            hits, mode = prefetch_project_memory_hits(
                pm,
                query,
                project_name=case["project"],
                semantic=sem,
                limit=5,
                semantic_enabled=True,
            )
            assert mode in ("vector", "keyword"), f"query={query!r} mode={mode}"
            bodies = " ".join(h.get("content") or "" for h in hits)
            assert any(
                tok in bodies for tok in stored.split()[:3]
            ) or stored[:12] in bodies, (
                f"query={query!r} missed stored={stored!r} hits={hits}"
            )

    def test_keyword_fallback_case(self, indexed_project):
        bm, pm, sem = indexed_project
        case = next(c for c in _load_cases() if c["id"] == "keyword_fallback")
        hits = search_project_memory_keywords(pm, "novel-factory 只读", limit=5)
        assert hits
        assert "novel-factory" in hits[0]["content"]

    def test_keyword_mode_when_semantic_disabled(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BUTLER_SEMANTIC_MEMORY", "0")
        proj_dir = tmp_path / "f"
        proj_dir.mkdir()
        (proj_dir / "project.yaml").write_text(
            f"name: p\nworkspace: {proj_dir}\n",
            encoding="utf-8",
        )
        pm = ProjectMemory(proj_dir)
        pm.markdown.append("Notes", "试点统一测试日 2026-05-22", classification="fact")
        hits, mode = prefetch_project_memory_hits(
            pm,
            "统一测试日期",
            project_name="p",
            semantic=None,
            limit=3,
            semantic_enabled=False,
        )
        assert mode == "keyword"
        assert any("2026-05-22" in (h.get("content") or "") for h in hits)

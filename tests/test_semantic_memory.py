"""Vector semantic memory P0: hashing embedder, index, hybrid recall."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from butler.memory import ButlerMemory
from butler.memory.embedding import HashingEmbedder, cosine_similarity, get_embedder
from butler.memory.semantic_config import semantic_memory_enabled
from butler.memory.semantic_index import SemanticMemoryIndex, hybrid_experience_search, index_experience_row
from butler.execution_context import use_execution_context
from butler.tools.registry import dispatch_tool


@pytest.mark.module_test
class TestHashingEmbedder:
    def test_similar_texts_have_higher_cosine_than_unrelated(self):
        emb = HashingEmbedder(dimension=64)
        a = emb.embed("一致性检查使用 pytest 框架")
        b = emb.embed("pytest 做一致性检查")
        c = emb.embed("今天天气很好适合出门")
        assert cosine_similarity(a, b) > cosine_similarity(a, c)

    def test_get_embedder_local_default(self):
        emb = get_embedder()
        assert emb.model_id
        assert len(emb.embed("测试")) == emb.dimension


@pytest.mark.module_test
class TestSemanticMemoryIndex:
    def test_upsert_search_and_hybrid(self, tmp_path):
        idx = SemanticMemoryIndex(tmp_path / "memory_vectors.db", HashingEmbedder(dimension=64))
        idx.upsert(
            source="experience",
            source_id="1",
            content="小说工厂一致性检查使用 pytest",
            project="灵文1号",
            category="experience",
        )
        idx.upsert(
            source="experience",
            source_id="2",
            content="完全无关的食堂菜单推荐",
            project="灵文1号",
            category="experience",
        )
        vec_hits = idx.search("pytest 一致性检查", project="灵文1号", limit=5)
        assert vec_hits
        assert "pytest" in vec_hits[0]["content"]

        fts_hits = [
            {"id": 2, "project": "灵文1号", "category": "experience", "content": "无关菜单"},
        ]
        hybrid = idx.hybrid_search("pytest 一致性", fts_hits, project="灵文1号", limit=3)
        assert any("pytest" in (h.get("content") or "") for h in hybrid)

    def test_skips_conversation_category(self, tmp_path):
        idx = SemanticMemoryIndex(tmp_path / "memory_vectors.db")
        idx.upsert(
            source="experience",
            source_id="9",
            content="Q: hi → A: hello",
            category="conversation",
        )
        assert idx.count_rows() == 0


@pytest.mark.module_test
class TestButlerMemorySemanticFlag:
    def test_semantic_disabled_by_default(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path / "butler_home"))
        from butler.config import reload_butler_settings

        reload_butler_settings()
        monkeypatch.delenv("BUTLER_SEMANTIC_MEMORY", raising=False)
        assert semantic_memory_enabled() is False
        bm = ButlerMemory(tmp_path / "home", tenant_id="default")
        assert bm.semantic is None

    def test_semantic_enabled_when_env_set(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BUTLER_SEMANTIC_MEMORY", "1")
        bm = ButlerMemory(tmp_path / "home", tenant_id="default")
        assert bm.semantic is not None
        row_id = bm.experience.add("p", "experience", "记住 pytest 一致性检查约定")
        index_experience_row(bm.semantic, row_id, project="p", category="experience", content="记住 pytest 一致性检查约定")
        hits = bm.semantic.search("一致性 pytest", project="p", limit=3)
        assert hits


@pytest.mark.module_test
class TestRecallHybridIntegration:
    def test_recall_uses_semantic_when_enabled(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BUTLER_SEMANTIC_MEMORY", "1")
        proj_dir = tmp_path / "p"
        proj_dir.mkdir()
        (proj_dir / "project.yaml").write_text(
            f"name: p\nworkspace: {proj_dir}\n",
            encoding="utf-8",
        )
        from butler.project import Project

        proj = Project.from_yaml(proj_dir / "project.yaml")
        bm = ButlerMemory(tmp_path / "home", tenant_id="default")
        row_id = bm.experience.add("p", "experience", "灵文1号采用 pytest 做守门测试")
        index_experience_row(
            bm.semantic,
            row_id,
            project="p",
            category="experience",
            content="灵文1号采用 pytest 做守门测试",
        )
        orch = MagicMock()  # noqa: magicmock-no-spec — semantic memory facade (orch)
        orch.memory_provider = None
        orch.butler_memory = bm
        orch._project_memory = None
        orch.project_manager.get_current.return_value = proj
        orch.project_manager.resolve_active_project_name.return_value = "p"

        with use_execution_context(orch, session_key="t:p"):
            raw = dispatch_tool(
                "butler_recall",
                {"scope": "experience", "query": "pytest 守门测试", "limit": 5},
            )
            out = json.loads(raw)
        assert out.get("semantic") is True
        results = out.get("results") or []
        assert results
        assert any("pytest" in (r.get("content") or "") for r in results)

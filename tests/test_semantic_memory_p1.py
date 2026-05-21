"""P1 semantic memory: project vectors, pending sync, diagnostics, embedders."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from butler.gateway.memory_commands import handle_memory_pending_command
from butler.memory import ButlerMemory
from butler.memory.embedding import HashingEmbedder, get_embedder
from butler.memory.semantic_index import SOURCE_PROJECT, SemanticMemoryIndex
from butler.memory.semantic_project import (
    index_pending_memory_bullet,
    index_project_memory_bullet,
    invalidate_pending_vector,
    pending_source_id,
    project_bullet_source_id,
)
from butler.memory.project_memory import ProjectMemory
from butler.execution_context import use_execution_context
from butler.tools.registry import dispatch_tool


@pytest.mark.module_test
class TestProjectMemoryVectors:
    def test_remember_fact_upserts_project_vector(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BUTLER_SEMANTIC_MEMORY", "1")
        proj_dir = tmp_path / "lw"
        proj_dir.mkdir()
        (proj_dir / "project.yaml").write_text(
            f"name: 灵文1号\nworkspace: {proj_dir}\n",
            encoding="utf-8",
        )
        from butler.project import Project

        proj = Project.from_yaml(proj_dir / "project.yaml")
        bm = ButlerMemory(tmp_path / "home", tenant_id="default")
        pm = ProjectMemory(proj_dir)
        orch = MagicMock()
        orch.butler_memory = bm
        orch._project_memory = pm
        orch.project_manager.get_current.return_value = proj
        orch.project_manager.resolve_active_project_name.return_value = "灵文1号"

        svc = __import__("butler.memory_plugin", fromlist=["ButlerMemoryService"]).ButlerMemoryService()
        svc._butler_global = bm
        svc._project_memory = pm

        raw = svc._remember(
            {
                "scope": "project_notes",
                "section": "Notes",
                "content": "试点验收日期 2026-05-21",
            }
        )
        out = json.loads(raw)
        assert out.get("classification") == "fact"
        assert bm.semantic is not None
        sid = project_bullet_source_id("灵文1号", "Notes", "试点验收日期 2026-05-21")
        hits = bm.semantic.search("验收日期", project="灵文1号", limit=5)
        assert any(h.get("source_id") == sid for h in hits)

    def test_remember_pending_then_approve_syncs_vectors(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BUTLER_SEMANTIC_MEMORY", "1")
        proj_dir = tmp_path / "lw"
        proj_dir.mkdir()
        (proj_dir / "project.yaml").write_text(
            f"name: p\nworkspace: {proj_dir}\n",
            encoding="utf-8",
        )
        from butler.project import Project

        proj = Project.from_yaml(proj_dir / "project.yaml")
        bm = ButlerMemory(tmp_path / "home", tenant_id="default")
        pm = ProjectMemory(proj_dir)
        pm.markdown.append("Decisions", "我们决定采用 PostgreSQL", classification="pending")

        sem = bm.semantic
        assert sem is not None
        index_pending_memory_bullet(sem, "p", "我们决定采用 PostgreSQL")
        pend_sid = pending_source_id("p", "我们决定采用 PostgreSQL")
        assert sem.count_rows() >= 1

        orch = MagicMock()
        orch.butler_memory = bm
        orch._project_memory = pm
        orch.project_manager.get_current.return_value = proj

        resp = handle_memory_pending_command(orch, "/批准记忆", "1")
        assert "已批准" in resp
        assert not pm.markdown.list_pending()
        formal_sid = project_bullet_source_id("p", "Decisions", "我们决定采用 PostgreSQL")
        with sem._lock:
            with sem._connect() as conn:
                row = conn.execute(
                    "SELECT source_id FROM memory_vectors WHERE source_id = ?",
                    (formal_sid,),
                ).fetchone()
                pend_row = conn.execute(
                    "SELECT source_id FROM memory_vectors WHERE source_id = ?",
                    (pend_sid,),
                ).fetchone()
        assert row is not None
        assert pend_row is None

    def test_invalidate_pending_vector(self, tmp_path):
        idx = SemanticMemoryIndex(tmp_path / "v.db", HashingEmbedder(dimension=32))
        index_pending_memory_bullet(idx, "p", "草稿记忆")
        sid = pending_source_id("p", "草稿记忆")
        assert idx.count_rows() == 1
        invalidate_pending_vector(idx, "p", "草稿记忆")
        with idx._lock:
            with idx._connect() as conn:
                row = conn.execute(
                    "SELECT 1 FROM memory_vectors WHERE source = ? AND source_id = ?",
                    (SOURCE_PROJECT, sid),
                ).fetchone()
        assert row is None


@pytest.mark.module_test
class TestDiagnosticsNoSession:
    def test_health_summary_without_turn_shows_memory_layers(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BUTLER_SEMANTIC_MEMORY", "1")
        from butler.gateway.message_handler import ButlerMessageHandler

        handler = ButlerMessageHandler(channel="test")
        handler._health_by_session.clear()
        text = handler._format_health_summary("default")
        assert "记忆分层" in text
        assert "Owner 画像" in text
        assert "向量索引" in text


@pytest.mark.module_test
class TestApiEmbedders:
    def test_get_embedder_openai_falls_back_without_key(self, monkeypatch):
        monkeypatch.setenv("BUTLER_EMBEDDING_PROVIDER", "openai")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        emb = get_embedder()
        assert emb.model_id == "hashing-v1"

    def test_get_embedder_openai_uses_api_when_configured(self, monkeypatch):
        monkeypatch.setenv("BUTLER_EMBEDDING_PROVIDER", "openai")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        monkeypatch.setenv("BUTLER_EMBEDDING_MODEL", "text-embedding-3-small")
        mock_emb = MagicMock()
        mock_emb.model_id = "openai/text-embedding-3-small"
        mock_emb.embed.return_value = [0.1, 0.2, 0.3]
        with patch("butler.memory.embedding._resolve_api_embedder", return_value=mock_emb):
            emb = get_embedder()
        assert emb.model_id.startswith("openai/")

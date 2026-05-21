"""Triplet display index, retrieval decay, and owner profile vectors."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from butler.memory.butler_memory import ButlerMemory
from butler.memory.retrieval_ranking import decay_factor, rerank_memory_hits
from butler.memory.semantic_index import SOURCE_OWNER_PROFILE, index_experience_row
from butler.memory.triplets import TripletIndex, extract_triplets_from_text


def test_extract_triplets_heuristic():
    text = "灵文1号采用 novel-factory；网关位于 wechat 通道"
    rows = extract_triplets_from_text(text)
    assert len(rows) >= 1
    assert rows[0]["subject"]
    assert rows[0]["relation"]
    assert rows[0]["object"]


def test_rerank_prefers_recent_and_accessed(monkeypatch):
    monkeypatch.setenv("BUTLER_MEMORY_HALF_LIFE_DAYS", "30")
    monkeypatch.setenv("BUTLER_MEMORY_ACCESS_BOOST", "0.2")
    now = time.time()
    hits = [
        {"content": "old", "score": 0.9, "created_at": now - 60 * 86400, "access_count": 0},
        {"content": "fresh", "score": 0.5, "created_at": now, "access_count": 10},
    ]
    ranked = rerank_memory_hits(hits, now=now)
    assert ranked[0]["content"] == "fresh"
    assert "rank_score" in ranked[0]


def test_decay_factor_monotonic():
    assert decay_factor(0, half_life_days=30) == 1.0
    assert decay_factor(30, half_life_days=30) < decay_factor(0, half_life_days=30)


def test_triplet_index_upsert_and_display(tmp_path):
    db = tmp_path / "memory_vectors.db"
    tri = TripletIndex(db)
    n = tri.upsert_from_content(
        content="试点项目采用 FastAPI",
        project="灵文1号",
        source="experience",
        source_ref="1",
    )
    assert n >= 1
    assert tri.count(project="灵文1号") >= 1
    text = tri.format_display(project="灵文1号", limit=5)
    assert "采用" in text or "FastAPI" in text


def test_profile_vector_sync_and_search(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_SEMANTIC_MEMORY", "1")
    home = tmp_path / "butler_home"
    bm = ButlerMemory(home, tenant_id="t1")
    assert bm.semantic is not None
    bm.profile.add("称呼主公，回复简洁")
    bm.profile.add("偏好技术栈 Python")
    indexed = bm.sync_profile_vectors()
    assert indexed == 2
    assert bm.semantic.count_by_source(SOURCE_OWNER_PROFILE) == 2
    hits = bm.search_profile_vectors("主公 称呼", limit=2)
    assert hits
    assert any("主公" in (h.get("content") or "") for h in hits)


def test_index_experience_row_triplets(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_SEMANTIC_MEMORY", "1")
    home = tmp_path / "butler_home2"
    bm = ButlerMemory(home, tenant_id="t2")
    row_id = bm.experience.add(
        project="p1",
        category="note",
        content="服务网关采用 Redis 队列",
    )
    index_experience_row(
        bm.semantic,
        row_id,
        project="p1",
        category="note",
        content="服务网关采用 Redis 队列",
    )
    tri = bm.triplet_index()
    assert tri is not None
    assert tri.count(project="p1") >= 1


def test_profile_remove_syncs_vectors(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_SEMANTIC_MEMORY", "1")
    home = tmp_path / "butler_home_rm"
    bm = ButlerMemory(home, tenant_id="t1")
    bm.profile.add("称呼主公")
    bm.sync_profile_vectors()
    assert bm.semantic.count_by_source(SOURCE_OWNER_PROFILE) == 1
    from butler.memory_plugin import ButlerMemoryProvider

    prov = ButlerMemoryProvider()
    prov._butler_global = bm
    raw = prov._remember(
        {
            "scope": "owner_profile",
            "action": "remove",
            "content": "称呼主公",
        }
    )
    import json

    data = json.loads(raw)
    assert data.get("ok") is True
    assert bm.semantic.count_by_source(SOURCE_OWNER_PROFILE) == 0


def test_pending_bullet_indexes_triplets(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_SEMANTIC_MEMORY", "1")
    from butler.memory.semantic_index import SemanticMemoryIndex
    from butler.memory.semantic_project import index_pending_memory_bullet

    db = tmp_path / "vec.db"
    sem = SemanticMemoryIndex(db)
    index_pending_memory_bullet(sem, "灵文1号", "试点模块采用 Redis 队列")
    from butler.memory.triplets import TripletIndex

    tri = TripletIndex(db)
    assert tri.count(project="灵文1号") >= 1


def test_memory_graph_command(tmp_path, monkeypatch):
    from butler.gateway.memory_commands import format_memory_triplet_graph
    from butler.orchestrator import ButlerOrchestrator

    monkeypatch.setenv("BUTLER_SEMANTIC_MEMORY", "1")
    home = tmp_path / "bh"
    bm = ButlerMemory(home, tenant_id="t3")
    tri = bm.triplet_index()
    assert tri is not None
    tri.upsert_from_content(
        content="模块A属于核心层",
        project="",
        source="test",
        source_ref="x",
    )

    class _Orch:
        butler_memory = bm
        project_manager = None

    text = format_memory_triplet_graph(_Orch())  # type: ignore[arg-type]
    assert "记忆图谱" in text
    assert "核心层" in text or "模块A" in text

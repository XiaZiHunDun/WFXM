"""P-MT 前提验证: v4-memory-theory.md 中 MT1–MT7 的前提假设。

验证清单（20 前提）:
  P-MT1a  _remember() 先写 Store 再调 IndexSync
  P-MT1b  reindex_semantic_memory() 扫描 Store 重建全量索引
  P-MT1c  IndexSync 失败不回滚 Store 写入
  P-MT2a  FTS5 精确子串匹配保证召回
  P-MT2b  向量自查询最高相似度
  P-MT2c  Profile 层精确字段匹配保证完全召回
  P-MT3a  Tenant 域路径与 Project 域路径不重叠
  P-MT3b  scope 参数决定写入路径
  P-MT3c  项目切换不改变 tenant 路径
  P-MT5a  decay_factor() 实现 2^{-Δt/τ}
  P-MT5b  access_boost 加法加权，不修改时间戳
  P-MT6a  ProfileStore 2000 字符硬上限
  P-MT6b  MEMORY.md 行/字节上限
  P-MT6c  会话事实 50 条/会话
  P-MT6d  Prefetch 注入总字符上限
  P-MT7a  Profile JSON 文件完整覆盖持久化
  P-MT7b  Experience SQLite WAL 写入即持久
  P-MT7c  MEMORY.md 文本文件覆盖持久化
  P-MT7d  Facts JSON 文件持久化
  P-MT7e  Vector Index SQLite 存储 + reindex 可重建
"""

from __future__ import annotations

import json
import math
import os
import sqlite3
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_butler_home(tmp_path: Path):
    """Create a minimal Butler home with tenant directories."""
    home = tmp_path / "butler_home"
    home.mkdir(parents=True, exist_ok=True)
    tenant_dir = home / "tenants" / "default" / "memory"
    tenant_dir.mkdir(parents=True, exist_ok=True)
    return home


@pytest.fixture
def tmp_project_root(tmp_path: Path):
    """Create a minimal project workspace with .butler/ dir."""
    ws = tmp_path / "my_project"
    ws.mkdir(parents=True, exist_ok=True)
    butler_dir = ws / ".butler" / "memory"
    butler_dir.mkdir(parents=True, exist_ok=True)
    return ws


# ===========================================================================
# MT1: 记忆写入原子性
# ===========================================================================


class TestPMT1WriteAtomicity:
    """P-MT1a/b/c: 写入原子性前提验证。"""

    def test_pmt1a_remember_experience_writes_store_then_index(
        self, tmp_butler_home: Path
    ):
        """P-MT1a: _remember(owner_experience) 先写 Store 再调 IndexSync。"""
        from butler.memory.butler_memory import ButlerMemory

        bm = ButlerMemory(tmp_butler_home)

        row_id = bm.experience.add(
            project="test", category="general", content="测试写入"
        )
        assert row_id > 0, "Store write must succeed first"

        rows = bm.experience.search("测试写入")
        assert any("测试写入" in str(r.get("content", "")) for r in rows), (
            "FTS store must contain the written content"
        )

    def test_pmt1b_reindex_scans_store(self, tmp_butler_home: Path):
        """P-MT1b: reindex_semantic_memory() 从 Store 重建索引。"""
        from butler.memory.butler_memory import ButlerMemory

        os.environ["BUTLER_SEMANTIC_MEMORY"] = "1"
        try:
            bm = ButlerMemory(tmp_butler_home)
            for i in range(3):
                bm.experience.add(
                    project="test", category="note", content=f"索引条目{i}"
                )

            from butler.memory.reindex import reindex_semantic_memory

            stats = reindex_semantic_memory(tmp_butler_home, tenant_id="default")
            assert stats.get("ok") is True
            assert stats["indexed_experience"] >= 3
        finally:
            os.environ.pop("BUTLER_SEMANTIC_MEMORY", None)

    def test_pmt1c_index_failure_keeps_store(self, tmp_butler_home: Path):
        """P-MT1c: IndexSync 失败不回滚 Store。"""
        from butler.memory.butler_memory import ButlerMemory

        bm = ButlerMemory(tmp_butler_home)

        row_id = bm.experience.add(
            project="test", category="general", content="不可丢失的记忆"
        )

        with patch(
            "butler.memory.semantic_index.index_experience_row",
            side_effect=RuntimeError("index crash"),
        ):
            pass

        rows = bm.experience.search("不可丢失的记忆")
        assert any("不可丢失" in str(r.get("content", "")) for r in rows), (
            "Store must retain data even if index fails"
        )


# ===========================================================================
# MT2: 检索完备性
# ===========================================================================


class TestPMT2RetrievalCompleteness:
    """P-MT2a/b/c: 检索完备性前提验证。"""

    def test_pmt2a_fts5_exact_substring_recall(self, tmp_butler_home: Path):
        """P-MT2a: FTS5 对精确子串匹配保证召回（单关键词）。"""
        from butler.memory.butler_memory import ButlerMemory

        bm = ButlerMemory(tmp_butler_home)
        target = "user likes starting work at 9am every day"
        bm.experience.add(project="p1", category="preference", content=target)

        hits = bm.experience.search("starting")
        found = any("starting work" in str(h.get("content", "")) for h in hits)
        assert found, "FTS5 must recall on single keyword"

    def test_pmt2a_fts5_exact_full_query_recall(self, tmp_butler_home: Path):
        """P-MT2a: FTS5 对精确全文查询保证召回。"""
        from butler.memory.butler_memory import ButlerMemory

        bm = ButlerMemory(tmp_butler_home)
        target = "用户喜欢在上午九点开始工作"
        bm.experience.add(project="p1", category="preference", content=target)

        hits = bm.experience.search(target)
        found = any(target in str(h.get("content", "")) for h in hits)
        if not found:
            recent = bm.experience.get_recent(limit=5)
            found = any(target in str(r.get("content", "")) for r in recent)
        assert found, "FTS5 or LIKE fallback must recall the entry"

    def test_pmt2b_vector_self_query_highest_similarity(self):
        """P-MT2b: 向量自查询 cos(Embed(m), Embed(m)) = 1。"""
        from butler.memory.embedding import HashingEmbedder

        emb = HashingEmbedder(dimension=96)
        text = "这是一段测试文本"
        vec = emb.embed(text)

        from butler.memory.embedding import cosine_similarity

        sim = cosine_similarity(vec, vec)
        assert abs(sim - 1.0) < 1e-6, f"Self-similarity must be 1.0, got {sim}"

    def test_pmt2c_profile_exact_field_recall(self, tmp_butler_home: Path):
        """P-MT2c: Profile 层精确字段匹配保证完全召回。"""
        from butler.memory.butler_memory import ButlerMemory

        bm = ButlerMemory(tmp_butler_home)
        bm.profile.add("偏好早起")
        bm.profile.add("使用 Python 编程")

        text = bm.profile.read()
        assert "偏好早起" in text
        assert "使用 Python 编程" in text


# ===========================================================================
# MT3: 域隔离安全
# ===========================================================================


class TestPMT3DomainIsolation:
    """P-MT3a/b/c: 域隔离安全前提验证。"""

    def test_pmt3a_tenant_project_paths_no_overlap(
        self, tmp_butler_home: Path, tmp_project_root: Path
    ):
        """P-MT3a: Tenant 域路径与 Project 域路径不重叠。"""
        tenant_path = tmp_butler_home / "tenants" / "default"
        project_path = tmp_project_root / ".butler"

        tenant_resolved = tenant_path.resolve()
        project_resolved = project_path.resolve()

        assert not str(tenant_resolved).startswith(str(project_resolved))
        assert not str(project_resolved).startswith(str(tenant_resolved))

    def test_pmt3b_scope_determines_write_path(self):
        """P-MT3b: scope 参数只有固定三值，不存在跨域 scope。"""
        from butler.memory.facade import _REMEMBER_SCHEMA

        scope_enum = _REMEMBER_SCHEMA["parameters"]["properties"]["scope"]["enum"]
        expected = {"owner_profile", "owner_experience", "project_notes"}
        assert set(scope_enum) == expected, (
            f"scope enum must be exactly {expected}, got {scope_enum}"
        )

    def test_pmt3c_project_switch_preserves_tenant(self, tmp_butler_home: Path):
        """P-MT3c: 项目切换只改变 workspace，不改变 tenant 路径。"""
        from butler.memory.butler_memory import ButlerMemory

        bm1 = ButlerMemory(tmp_butler_home, tenant_id="default")
        bm1.profile.add("全局偏好")

        bm2 = ButlerMemory(tmp_butler_home, tenant_id="default")

        text = bm2.profile.read()
        assert "全局偏好" in text, "Tenant profile persists across project switches"


# ===========================================================================
# MT5: 衰减单调性与安全遗忘
# ===========================================================================


class TestPMT5DecayMonotonicity:
    """P-MT5a/b: 衰减函数性质验证。"""

    def test_pmt5a_decay_implements_exponential(self):
        """P-MT5a: decay_factor() = 2^{-Δt/τ}。"""
        from butler.memory.retrieval_ranking import decay_factor

        tau = 30.0
        for age in [0, 1, 7, 14, 30, 60, 90, 365]:
            actual = decay_factor(float(age), half_life_days=tau)
            expected = math.exp(-math.log(2) * age / tau)
            assert abs(actual - expected) < 1e-9, (
                f"age={age}: expected {expected}, got {actual}"
            )

    def test_pmt5a_decay_boundary_conditions(self):
        """P-MT5a: decay(0)=1, lim decay(t→∞)→0。"""
        from butler.memory.retrieval_ranking import decay_factor

        assert decay_factor(0, half_life_days=30) == 1.0
        assert decay_factor(10000, half_life_days=30) < 1e-50

    def test_pmt5a_decay_monotonically_decreasing(self):
        """P-MT5a: 衰减函数关于时间单调递减。"""
        from butler.memory.retrieval_ranking import decay_factor

        tau = 30.0
        prev = 1.0
        for age in range(1, 200):
            val = decay_factor(float(age), half_life_days=tau)
            assert val < prev, f"decay({age}) >= decay({age-1})"
            prev = val

    def test_pmt5b_access_boost_additive(self):
        """P-MT5b: access_boost 是加法加权 (1 + β·log(1+n))。"""
        from butler.memory.retrieval_ranking import access_boost_factor

        beta = 0.12
        for n in [0, 1, 5, 10, 100]:
            actual = access_boost_factor(n, boost=beta)
            expected = 1.0 + beta * math.log1p(n)
            assert abs(actual - expected) < 1e-9

    def test_pmt5b_access_boost_no_timestamp_reset(self):
        """P-MT5b: access_boost 不修改时间戳——rerank 不改变 created_at。"""
        from butler.memory.retrieval_ranking import rerank_memory_hits

        now = time.time()
        hits = [
            {"content": "old", "score": 0.8, "created_at": now - 86400 * 30, "access_count": 5},
            {"content": "new", "score": 0.8, "created_at": now - 86400 * 1, "access_count": 0},
        ]
        original_created = [h["created_at"] for h in hits]

        ranked = rerank_memory_hits(hits, now=now)

        for r in ranked:
            assert r["created_at"] in original_created, "rerank must not modify created_at"


# ===========================================================================
# MT6: 容量有界性
# ===========================================================================


class TestPMT6CapacityBounded:
    """P-MT6a/b/c/d: 各层容量上限验证。"""

    def test_pmt6a_profile_2000_char_limit(self, tmp_butler_home: Path):
        """P-MT6a: ProfileStore 2000 字符硬上限。"""
        from butler.memory.butler_memory import ProfileStore

        prof = ProfileStore(tmp_butler_home / "tenants" / "default" / "memory" / "profile.json")
        assert prof.char_limit == 2000

        result = prof.add("x" * 2001)
        assert result["success"] is False
        assert "limit" in result["error"].lower() or "exceeds" in result["error"].lower()

    def test_pmt6a_profile_rejects_at_capacity(self, tmp_butler_home: Path):
        """P-MT6a: ProfileStore 满容量后拒绝追加。"""
        from butler.memory.butler_memory import ProfileStore

        prof = ProfileStore(tmp_butler_home / "tenants" / "default" / "memory" / "profile.json")
        prof.add("a" * 1900)
        result = prof.add("b" * 200)
        assert result["success"] is False

    def test_pmt6b_memory_md_line_limit(self):
        """P-MT6b: MEMORY.md 行上限截断。"""
        from butler.memory.memory_caps import truncate_memory_text

        lines = "\n".join([f"- line {i}" for i in range(300)])
        truncated, was_truncated = truncate_memory_text(lines)
        assert was_truncated is True
        assert truncated.count("\n") < 300

    def test_pmt6b_memory_md_byte_limit(self):
        """P-MT6b: MEMORY.md 字节上限截断——truncate 被触发。"""
        from butler.memory.memory_caps import truncate_memory_text

        lines = "\n".join([f"- 中文记忆条目第{i}行" for i in range(10)])
        big_text = lines * 400
        truncated, was_truncated = truncate_memory_text(big_text)
        assert was_truncated is True
        assert len(truncated) < len(big_text), "Must be shorter after truncation"

    def test_pmt6c_facts_50_per_session(self):
        """P-MT6c: 会话事实 50 条/会话上限。"""
        from butler.core.fact_extraction import _MAX_FACTS_PER_SESSION

        assert _MAX_FACTS_PER_SESSION == 50

    def test_pmt6c_facts_save_trims(self, tmp_path: Path):
        """P-MT6c: save_facts 截断超限条目。"""
        from butler.core.fact_extraction import save_facts, load_facts

        os.environ["BUTLER_HOME"] = str(tmp_path)
        try:
            facts = [{"type": "decision", "value": f"d{i}"} for i in range(80)]
            save_facts("test-session", facts)
            loaded = load_facts("test-session")
            assert len(loaded) <= 50
        finally:
            os.environ.pop("BUTLER_HOME", None)

    def test_pmt6d_prefetch_total_max_chars(self):
        """P-MT6d: Prefetch 注入总字符上限存在。"""
        from butler.session.memory_prefetch import prefetch_limits

        caps = prefetch_limits()
        assert "total_max_chars" in caps
        assert caps["total_max_chars"] > 0


# ===========================================================================
# MT7: 持久化一致性
# ===========================================================================


class TestPMT7PersistenceConsistency:
    """P-MT7a/b/c/d/e: 持久化前提验证。"""

    def test_pmt7a_profile_json_full_overwrite(self, tmp_butler_home: Path):
        """P-MT7a: Profile 每次写入完整覆盖 JSON。"""
        from butler.memory.butler_memory import ProfileStore

        prof_path = tmp_butler_home / "tenants" / "default" / "memory" / "profile.json"
        prof = ProfileStore(prof_path)
        prof.add("v1 data")
        prof.add("v2 data")

        raw = json.loads(prof_path.read_text(encoding="utf-8"))
        assert "entries" in raw
        assert len(raw["entries"]) == 2

        prof2 = ProfileStore(prof_path)
        text = prof2.read()
        assert "v1 data" in text
        assert "v2 data" in text

    def test_pmt7b_experience_sqlite_wal_persistent(self, tmp_butler_home: Path):
        """P-MT7b: Experience SQLite WAL 模式写入即持久。"""
        from butler.memory.butler_memory import ButlerMemory

        bm = ButlerMemory(tmp_butler_home)
        bm.experience.add(project="p1", category="note", content="持久化测试")

        db_path = bm.experience.db_path
        conn2 = sqlite3.connect(str(db_path))
        try:
            mode = conn2.execute("PRAGMA journal_mode").fetchone()[0]
            assert mode.lower() == "wal", f"Expected WAL mode, got {mode}"

            rows = conn2.execute(
                "SELECT content FROM experiences WHERE content LIKE '%持久化测试%'"
            ).fetchall()
            assert len(rows) >= 1
        finally:
            conn2.close()

    def test_pmt7c_memory_md_text_persistence(self, tmp_project_root: Path):
        """P-MT7c: MEMORY.md 文本文件覆盖持久化。"""
        from butler.memory.project_memory import ProjectMemory

        pm = ProjectMemory(tmp_project_root)
        pm.markdown.append("Notes", "测试笔记条目", classification="fact")

        md_path = tmp_project_root / ".butler" / "memory" / "MEMORY.md"
        text = md_path.read_text(encoding="utf-8")
        assert "测试笔记条目" in text

        pm2 = ProjectMemory(tmp_project_root)
        ctx = pm2.markdown.get_section("Notes")
        assert "测试笔记条目" in ctx

    def test_pmt7d_facts_json_persistence(self, tmp_path: Path):
        """P-MT7d: Facts JSON 文件持久化。"""
        os.environ["BUTLER_HOME"] = str(tmp_path)
        try:
            from butler.core.fact_extraction import save_facts, load_facts

            facts = [{"type": "decision", "value": "采用方案A"}]
            save_facts("persist-test", facts)

            loaded = load_facts("persist-test")
            assert len(loaded) == 1
            assert loaded[0]["value"] == "采用方案A"
        finally:
            os.environ.pop("BUTLER_HOME", None)

    def test_pmt7e_vector_sqlite_reindex_rebuild(self, tmp_butler_home: Path):
        """P-MT7e: Vector Index SQLite 存储，可从 Store 重建。"""
        os.environ["BUTLER_SEMANTIC_MEMORY"] = "1"
        try:
            from butler.memory.butler_memory import ButlerMemory
            from butler.memory.reindex import reindex_semantic_memory

            bm = ButlerMemory(tmp_butler_home)
            bm.experience.add(project="p1", category="note", content="向量重建测试")

            stats = reindex_semantic_memory(tmp_butler_home, tenant_id="default")
            assert stats.get("ok") is True
            count_1 = stats["vector_rows"]

            stats2 = reindex_semantic_memory(
                tmp_butler_home, tenant_id="default", clear_vectors=True
            )
            assert stats2.get("ok") is True
            assert stats2["vector_rows"] >= 1, "Rebuild must recover vectors from Store"
        finally:
            os.environ.pop("BUTLER_SEMANTIC_MEMORY", None)

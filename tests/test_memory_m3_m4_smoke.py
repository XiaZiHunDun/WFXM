"""WeChat memory smoke M3 (reject pending) and M4 (prefetch cache hit)."""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from butler.gateway.memory_commands import handle_memory_pending_command
from butler.memory import ButlerMemory
from butler.memory.prefetch_cache import clear_prefetch_cache
from butler.memory.project_memory import ProjectMemory
from butler.memory.semantic_project import index_pending_memory_bullet, pending_source_id
from butler.project import Project
from butler.session.lifecycle import prefetch_turn_memory, queue_prefetch_after_turn


@pytest.mark.module_test
class TestM3RejectPendingGateway:
    def test_reject_via_slash_command(self, tmp_path, monkeypatch):
        """M3: 决策句进 Pending → /拒绝记忆 1 → 向量清除、无正式条目."""
        monkeypatch.setenv("BUTLER_SEMANTIC_MEMORY", "1")
        proj_dir = tmp_path / "lw"
        proj_dir.mkdir()
        (proj_dir / "project.yaml").write_text(
            f"name: 灵文1号\nworkspace: {proj_dir}\n",
            encoding="utf-8",
        )
        proj = Project.from_yaml(proj_dir / "project.yaml")
        bm = ButlerMemory(tmp_path / "home", tenant_id="default")
        pm = ProjectMemory(proj_dir)
        pm.markdown.append(
            "Decisions",
            "我们决定下周用 Redis 做缓存试点",
            classification="pending",
        )
        index_pending_memory_bullet(bm.semantic, "灵文1号", "我们决定下周用 Redis 做缓存试点")
        pend_sid = pending_source_id("灵文1号", "我们决定下周用 Redis 做缓存试点")

        orch = MagicMock()
        orch.butler_memory = bm
        orch._project_memory = pm
        orch.project_manager.get_current.return_value = proj
        orch._reload_project_memory = MagicMock()

        listed = handle_memory_pending_command(orch, "/记忆待审", "")
        assert "1." in listed
        assert "Redis" in listed

        out = handle_memory_pending_command(orch, "/拒绝记忆", "1")
        assert out and "已拒绝" in out
        assert not pm.markdown.list_pending()
        assert "Redis" not in pm.markdown.get_section("Decisions")

        with bm.semantic._lock:
            conn = bm.semantic._conn
            assert (
                conn.execute(
                    "SELECT 1 FROM memory_vectors WHERE source_id = ?",
                    (pend_sid,),
                ).fetchone()
                is None
            )


@pytest.mark.module_test
class TestM4PrefetchCacheHit:
    def test_repeat_query_hits_warm_cache(self, tmp_path, monkeypatch):
        """M4: 同一句 query 在 queue_prefetch warm 后命中缓存."""
        monkeypatch.setenv("BUTLER_SEMANTIC_MEMORY", "1")
        monkeypatch.setenv("BUTLER_QUEUE_PREFETCH", "1")
        clear_prefetch_cache()

        proj_dir = tmp_path / "lw"
        proj_dir.mkdir()
        (proj_dir / "project.yaml").write_text(
            f"name: 灵文1号\nworkspace: {proj_dir}\n",
            encoding="utf-8",
        )
        proj = Project.from_yaml(proj_dir / "project.yaml")
        bm = ButlerMemory(tmp_path / "home", tenant_id="default")
        pm = ProjectMemory(proj_dir)
        pm.markdown.append(
            "Notes",
            "试点统一测试日 2026-05-22",
            classification="fact",
        )
        from butler.memory.semantic_project import index_project_memory_bullet

        index_project_memory_bullet(
            bm.semantic, "灵文1号", "Notes", "试点统一测试日 2026-05-22"
        )

        orch = MagicMock()
        orch.butler_memory = bm
        orch._project_memory = pm
        orch.project_manager.resolve_active_project_name.return_value = "灵文1号"
        orch.project_manager.get_current.return_value = proj

        query = "灵文试点统一测试是哪天"
        session_id = "wechat:user@im.wechat:灵文1号"

        # 模拟首轮：预取 + 轮末 warm
        prefetch_turn_memory(orch, query, use_cache=False)
        queue_prefetch_after_turn(orch, query, session_id=session_id)
        time.sleep(0.3)

        diagnostics: dict = {}
        with pytest.MonkeyPatch.context() as m:
            m.setattr(
                "butler.session.lifecycle._session_key_for_prefetch",
                lambda: session_id,
            )
            prefetch_turn_memory(
                orch,
                query,
                diagnostics=diagnostics,
                use_cache=True,
            )

        assert diagnostics.get("memory_prefetch_cache_hit") is True

    def test_diagnostics_line_for_cache_hit(self):
        from butler.memory.diagnostics import format_memory_diagnostic_lines

        lines = "\n".join(
            format_memory_diagnostic_lines(
                {
                    "memory_prefetch_cache_hit": True,
                    "semantic_enabled": True,
                    "vector_rows": 4,
                    "vector_model": "hashing-v1",
                }
            )
        )
        assert "上轮预取缓存" in lines
        assert "命中" in lines

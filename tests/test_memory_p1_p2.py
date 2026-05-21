"""P1/P2 memory & pilot workflow (personal butler, single tenant)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml

from butler.gateway.memory_commands import (
    format_pending_memory_list,
    handle_memory_pending_command,
)
from butler.gateway.message_handler import ButlerMessageHandler, _is_sessionless_command
from butler.memory.project_memory import ProjectMemory
from butler.project import Project
from butler.tools.path_safety import prepare_shell_command
from butler.workflows.loader import resolve_workflow


@pytest.mark.module_test
class TestPendingMemoryCommands:
    def test_list_and_approve_pending(self, tmp_path):
        proj_dir = tmp_path / "p"
        proj_dir.mkdir()
        (proj_dir / "project.yaml").write_text(
            f"name: demo\nworkspace: {proj_dir}\n",
            encoding="utf-8",
        )
        proj = Project.from_yaml(proj_dir / "project.yaml")
        pm = ProjectMemory(proj_dir)
        pm.markdown.append("Decisions", "我们决定采用 pytest", classification="auto")

        orch = MagicMock()
        orch._project_memory = pm
        orch._reload_project_memory = MagicMock()

        listed = format_pending_memory_list(orch)
        assert "1." in listed
        assert "pytest" in listed

        ok = handle_memory_pending_command(orch, "/批准记忆", "1")
        assert ok and "已批准" in ok
        assert not pm.markdown.list_pending()
        body = pm.markdown.get_section("Decisions")
        assert "pytest" in body

    def test_approve_all(self, tmp_path):
        proj_dir = tmp_path / "p2"
        proj_dir.mkdir()
        pm = ProjectMemory(proj_dir)
        pm.markdown.append("Notes", "待定方案 A", classification="pending")
        pm.markdown.append("Notes", "待定方案 B", classification="pending")
        orch = MagicMock()
        orch._project_memory = pm
        orch._reload_project_memory = MagicMock()

        out = handle_memory_pending_command(orch, "/批准记忆", "全部")
        assert "2" in out
        assert not pm.markdown.list_pending()

    def test_reject_pending_clears_vector(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BUTLER_SEMANTIC_MEMORY", "1")
        from butler.memory import ButlerMemory
        from butler.memory.semantic_project import (
            index_pending_memory_bullet,
            pending_source_id,
        )

        proj_dir = tmp_path / "p3"
        proj_dir.mkdir()
        (proj_dir / "project.yaml").write_text(
            f"name: p\nworkspace: {proj_dir}\n",
            encoding="utf-8",
        )
        proj = Project.from_yaml(proj_dir / "project.yaml")
        bm = ButlerMemory(tmp_path / "home", tenant_id="default")
        pm = ProjectMemory(proj_dir)
        pm.markdown.append("Decisions", "我们决定采用 Kafka", classification="pending")
        index_pending_memory_bullet(bm.semantic, "p", "我们决定采用 Kafka")
        pend_sid = pending_source_id("p", "我们决定采用 Kafka")

        orch = MagicMock()
        orch.butler_memory = bm
        orch._project_memory = pm
        orch.project_manager.get_current.return_value = proj
        orch._reload_project_memory = MagicMock()

        out = handle_memory_pending_command(orch, "/拒绝记忆", "1")
        assert out and "已拒绝" in out
        assert not pm.markdown.list_pending()
        with bm.semantic._lock:
            with bm.semantic._connect() as conn:
                assert (
                    conn.execute(
                        "SELECT 1 FROM memory_vectors WHERE source_id = ?",
                        (pend_sid,),
                    ).fetchone()
                    is None
                )


@pytest.mark.module_test
class TestNovelFactoryStatusWorkflow:
    def test_builtin_resolves_with_steps(self, tmp_path):
        proj_dir = tmp_path / "lw"
        proj_dir.mkdir()
        (proj_dir / "project.yaml").write_text(
            yaml.safe_dump(
                {
                    "name": "灵文1号",
                    "workspace": str(proj_dir),
                    "workflows": [{"name": "novel-factory-status"}],
                },
                allow_unicode=True,
            ),
            encoding="utf-8",
        )
        proj = Project.from_yaml(proj_dir / "project.yaml")
        wf = resolve_workflow(proj, "novel-factory-status")
        assert wf is not None
        assert wf.runnable
        assert len(wf.steps) == 2
        assert wf.steps[0].id == "read-state"


@pytest.mark.module_test
class TestTerminalExtraAllowlist:
    def test_python3_allowed_when_extra_env(self, monkeypatch):
        monkeypatch.setenv("BUTLER_ENABLE_TERMINAL", "1")
        monkeypatch.setenv("BUTLER_TERMINAL_ALLOWLIST_EXTRA", "python3,bash")
        result = prepare_shell_command("python3 --version")
        assert result.allowed, result.error

    def test_python3_blocked_without_extra(self, monkeypatch):
        monkeypatch.delenv("BUTLER_TERMINAL_ALLOWLIST_EXTRA", raising=False)
        result = prepare_shell_command("python3 --version")
        assert not result.allowed


@pytest.mark.module_test
class TestGatewayMemorySlashRegistration:
    def test_sessionless_includes_memory_commands(self):
        assert _is_sessionless_command("/记忆待审")
        assert _is_sessionless_command("/批准记忆 1")
        assert _is_sessionless_command("/拒绝记忆 1")

    def test_status_shows_env_default_project(self, monkeypatch):
        monkeypatch.setenv("BUTLER_DEFAULT_PROJECT", "灵文1号")
        handler = ButlerMessageHandler(channel="gateway")
        with pytest.MonkeyPatch.context() as m:
            m.setattr(
                handler._orchestrator.project_manager,
                "resolve_active_project_name",
                lambda session_key="": "灵文1号",
            )
            text = handler._handle_command("/状态", session_key="wechat:u1:_")
        assert "环境默认项目" in text
        assert "灵文1号" in text


@pytest.mark.module_test
class TestExperiencePrune:
    def test_prune_old_conversation_rows(self, tmp_path):
        import time
        from butler.memory.butler_memory import ButlerMemory

        bm = ButlerMemory(tmp_path / "bh")
        old = time.time() - 40 * 86400
        with bm.experience._lock:
            with bm.experience._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO experiences (project, category, content, tags, created_at)
                    VALUES ('', 'conversation', 'old', '', ?)
                    """,
                    (old,),
                )
                conn.commit()
        removed = bm.experience.prune_conversation_older_than(30)
        assert removed >= 1

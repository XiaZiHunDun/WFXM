"""project_notes remove/replace keeps vectors in sync."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from butler.memory import ButlerMemory
from butler.memory.project_memory import ProjectMemory
from butler.memory.semantic_project import project_bullet_source_id
from butler.memory_plugin import ButlerMemoryService
from butler.execution_context import use_execution_context


@pytest.mark.module_test
class TestMemoryBulletEdit:
    def test_remove_and_replace_update_vectors(self, tmp_path, monkeypatch):
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
        pm = ProjectMemory(proj_dir)
        pm.markdown.append("Notes", "旧日期 2026-05-21", classification="fact")

        svc = ButlerMemoryService()
        svc._butler_global = bm
        svc._project_memory = pm
        orch = MagicMock()
        orch.butler_memory = bm
        orch._project_memory = pm
        orch.project_manager.get_current.return_value = proj
        orch.project_manager.resolve_active_project_name.return_value = "p"

        old_sid = project_bullet_source_id("p", "Notes", "旧日期 2026-05-21")

        with use_execution_context(orch, session_key="t:p"):
            raw = svc._remember(
                {
                    "scope": "project_notes",
                    "section": "Notes",
                    "action": "replace",
                    "old_content": "旧日期 2026-05-21",
                    "content": "试点统一测试日 2026-05-22",
                }
            )
        assert json.loads(raw).get("ok") is True

        new_sid = project_bullet_source_id("p", "Notes", "试点统一测试日 2026-05-22")
        with bm.semantic._lock:
            with bm.semantic._connect() as conn:
                old_row = conn.execute(
                    "SELECT 1 FROM memory_vectors WHERE source_id = ?",
                    (old_sid,),
                ).fetchone()
                new_row = conn.execute(
                    "SELECT 1 FROM memory_vectors WHERE source_id = ?",
                    (new_sid,),
                ).fetchone()
        assert old_row is None
        assert new_row is not None

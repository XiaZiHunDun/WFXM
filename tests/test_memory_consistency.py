"""Memory consistency fixes: remember→Pending, recall excludes conversation."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from butler.execution_context import use_execution_context
from butler.memory import ButlerMemory, ProjectMemory
from butler.memory.project_memory import normalize_section_name
from butler.project import Project
from butler.tools.registry import dispatch_tool


@pytest.mark.module_test
class TestRememberPendingAlignment:
    def test_project_notes_decision_goes_pending(self, tmp_path, monkeypatch):
        proj_dir = tmp_path / "LingWen1"
        proj_dir.mkdir()
        (proj_dir / "project.yaml").write_text(
            f"name: demo\nworkspace: {proj_dir}\n",
            encoding="utf-8",
        )
        proj = Project.from_yaml(proj_dir / "project.yaml")
        bm = ButlerMemory(tmp_path / "butler_home", tenant_id="default")
        orch = MagicMock()  # noqa: magicmock-no-spec — complex facade, spec= 收益低
        orch.memory_provider = None
        orch.butler_memory = bm
        orch._project_memory = ProjectMemory(proj_dir)
        orch.project_manager.get_current.return_value = proj

        with use_execution_context(orch, session_key="test:u1:demo"):
            out = json.loads(
                dispatch_tool(
                    "butler_remember",
                    {
                        "scope": "project_notes",
                        "section": "Decisions",
                        "content": "我们决定采用 PostgreSQL 作为主库",
                    },
                )
            )
        assert out.get("ok") is True
        assert out.get("classification") == "pending"
        pm = ProjectMemory(proj_dir)
        assert pm.markdown.list_pending()
        assert "PostgreSQL" in pm.markdown.list_pending()[0]["content"]

    def test_project_notes_plain_fact_stays_in_section(self, tmp_path, monkeypatch):
        proj_dir = tmp_path / "p"
        proj_dir.mkdir()
        (proj_dir / "project.yaml").write_text(
            f"name: p\nworkspace: {proj_dir}\n",
            encoding="utf-8",
        )
        proj = Project.from_yaml(proj_dir / "project.yaml")
        bm = ButlerMemory(tmp_path / "butler_home", tenant_id="default")
        orch = MagicMock()  # noqa: magicmock-no-spec — complex facade, spec= 收益低
        orch.memory_provider = None
        orch.butler_memory = bm
        orch._project_memory = ProjectMemory(proj_dir)
        orch.project_manager.get_current.return_value = proj

        with use_execution_context(orch, session_key="test:u1:p"):
            raw = dispatch_tool(
                "butler_remember",
                {
                    "scope": "project_notes",
                    "section": "Notes",
                    "content": "试点进度：记忆一致性验收",
                },
            )
            out = json.loads(raw)
        assert out.get("classification") == "fact"
        pm = ProjectMemory(proj_dir)
        assert "试点进度" in pm.markdown.get_section("Notes")
        assert not pm.markdown.list_pending()


@pytest.mark.module_test
class TestRecallFiltersConversation:
    def test_recall_excludes_conversation_category(self, tmp_path):
        proj_dir = tmp_path / "p"
        proj_dir.mkdir()
        bm = ButlerMemory(tmp_path / "butler_home", tenant_id="default")
        bm.experience.add("", "conversation", "Q: hi → A: hello", tags="session:test")
        bm.experience.add("", "delegation_note", "长期：一致性检查用 pytest", tags="")

        orch = MagicMock()  # noqa: magicmock-no-spec — complex facade, spec= 收益低
        orch.butler_memory = bm
        orch._project_memory = None
        orch.memory_provider = None
        orch.project_manager.get_current.return_value = None

        with use_execution_context(orch, session_key="test:u1:p"):
            out = json.loads(dispatch_tool("butler_recall", {"scope": "experience", "limit": 10}))

        assert out.get("ok") is True
        rows = out.get("results") or []
        assert all((r.get("category") or "") != "conversation" for r in rows)
        assert any("pytest" in (r.get("content") or "") for r in rows)


@pytest.mark.module_test
class TestSectionNormalization:
    def test_chinese_section_alias(self):
        assert normalize_section_name("架构与设计") == "Architecture"
        assert normalize_section_name("关键决策") == "Decisions"
        assert normalize_section_name("Notes") == "Notes"

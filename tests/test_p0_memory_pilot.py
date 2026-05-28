"""P0 pilot memory: guide doc, tools, sync policy, /new summary (automated gate)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from butler.core.agent_loop import LoopStatus
from butler.execution_context import use_execution_context
from butler.gateway.message_handler import ButlerMessageHandler
from butler.memory.project_memory import ProjectMemory
from butler.project import Project
from butler.session.lifecycle import (
    conversation_sync_enabled,
    format_session_end_summary,
    should_sync_conversation_turn,
    sync_turn_memory,
)
from butler.tools.registry import dispatch_tool, get_tool_definitions

_REPO = Path(__file__).resolve().parents[1]
_GUIDE = _REPO / "projects" / "LingWen1" / "docs" / "memory-guide.md"


@pytest.mark.module_test
class TestPilotMemoryGuide:
    def test_memory_guide_exists_and_covers_layers(self):
        assert _GUIDE.is_file()
        text = _GUIDE.read_text(encoding="utf-8")
        assert "灵文1号" in text
        assert "owner_profile" in text
        assert "project_notes" in text
        assert "BUTLER_SYNC_CONVERSATION_MEMORY" in text
        assert "novel-factory" in text

    def test_pilot_setup_links_memory_guide(self):
        pilot = _REPO / "projects" / "LingWen1" / "docs" / "pilot-setup.md"
        assert "memory-guide.md" in pilot.read_text(encoding="utf-8")


@pytest.mark.module_test
class TestMemoryToolsDispatch:
    def test_remember_profile_and_project_notes(self, tmp_path, monkeypatch):
        from butler.memory.butler_memory import ButlerMemory
        from unittest.mock import MagicMock

        proj_dir = tmp_path / "LingWen1"
        proj_dir.mkdir()
        (proj_dir / "project.yaml").write_text(
            f"name: 灵文1号\ntype: content\nworkspace: {proj_dir}\n",
            encoding="utf-8",
        )
        proj = Project.from_yaml(proj_dir / "project.yaml")
        bm = ButlerMemory(tmp_path / "butler_home", tenant_id="default")
        orch = MagicMock()
        orch.memory_provider = None
        orch.butler_memory = bm
        orch._project_memory = ProjectMemory(proj_dir)
        orch.project_manager.get_current.return_value = proj

        with use_execution_context(orch, session_key="test:u1:灵文1号"):
            prof = json.loads(
                dispatch_tool(
                    "butler_remember",
                    {"scope": "owner_profile", "content": "自动化：称呼主公"},
                )
            )
            assert prof.get("ok") is True

            notes = json.loads(
                dispatch_tool(
                    "butler_remember",
                    {
                        "scope": "project_notes",
                        "section": "Notes",
                        "content": "试点进度：记忆工具验收",
                    },
                )
            )
            assert notes.get("ok") is True

            memory_md = (proj_dir / ".butler" / "memory" / "MEMORY.md").read_text(
                encoding="utf-8"
            )
            assert "试点进度" in memory_md

            recall = json.loads(dispatch_tool("butler_recall", {"scope": "profile"}))
            assert "主公" in recall.get("profile", "")


@pytest.mark.module_test
class TestConversationSyncPolicy:
    def test_default_off_unless_explicit_remember(self, monkeypatch):
        monkeypatch.setenv("BUTLER_SYNC_CONVERSATION_MEMORY", "0")
        assert conversation_sync_enabled() is False
        assert should_sync_conversation_turn("你好", "你好") is False
        assert should_sync_conversation_turn("请记住：灵文1号", "好的") is True

    def test_format_session_end_summary_strings(self):
        assert "已提炼" in format_session_end_summary({"memory_updates": 1})
        assert "对话过短" in format_session_end_summary(
            {"skipped": True, "reason": "short_history"}
        )


@pytest.mark.module_test
class TestNewCommandMemoryFeedback:
    def test_new_appends_extraction_summary(self, monkeypatch):
        from unittest.mock import MagicMock, patch

        handler = ButlerMessageHandler(channel="gateway")
        loop = MagicMock(messages=[{"role": "user"}] * 6)
        handler._sessions["wechat:u1:_"] = loop

        with patch(
            "butler.session.lifecycle.trigger_session_end",
            return_value={"memory_updates": 2, "skills_extracted": 0},
        ):
            text = handler._handle_command("/新对话", session_key="wechat:u1:_")

        assert text.startswith("已清空本轮对话上下文。")
        assert "已提炼" in text
        assert "wechat:u1:_" not in handler._sessions


@pytest.mark.module_test
class TestToolRegistryIncludesMemory:
    def test_memory_tools_registered(self):
        names = {t["function"]["name"] for t in get_tool_definitions()}
        assert "butler_remember" in names
        assert "butler_recall" in names

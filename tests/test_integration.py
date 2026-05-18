"""Integration tests — Butler init, project switch memory isolation, post-session processor."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from butler.storage.butler_memory import ButlerMemory
from butler.storage.project_memory import ProjectMemory


class TestButlerInit:
    def test_butler_init_default(self):
        from butler.core.butler import Butler
        b = Butler()
        assert b.user_id == "owner"
        assert b.channel == "cli"
        assert b.session_id is not None
        assert len(b.session_id) > 0
        asyncio.run(b.close())

    def test_butler_custom_params(self):
        from butler.core.butler import Butler
        b = Butler(user_id="test_user", channel="wechat")
        assert b.user_id == "test_user"
        assert b.channel == "wechat"
        asyncio.run(b.close())

    def test_butler_system_prompt_built(self):
        from butler.core.butler import Butler
        b = Butler()
        assert len(b._system_prompt) > 100
        assert "莎丽" in b._system_prompt
        asyncio.run(b.close())

    def test_butler_tools_loaded(self):
        from butler.core.butler import Butler
        from butler.tools.registry import tool_registry
        b = Butler()
        defs = tool_registry.get_definitions()
        assert len(defs) > 20
        tool_names = [d["function"]["name"] for d in defs]
        assert "list_projects" in tool_names
        assert "read_file" in tool_names
        assert "remember" in tool_names
        assert "skill_list" in tool_names
        asyncio.run(b.close())


class TestProjectSwitchMemoryIsolation:
    def test_switch_changes_session(self):
        from butler.core.butler import Butler
        from butler.core.project_manager import project_manager

        b = Butler()
        old_session = b.session_id

        project_manager.switch_project("灵文")
        new_session = b.session_id

        assert old_session != new_session or project_manager.current_project == "灵文"
        asyncio.run(b.close())

    def test_project_memory_isolation(self, tmp_dir):
        ws_a = tmp_dir / "project_a"
        ws_a.mkdir()
        ws_b = tmp_dir / "project_b"
        ws_b.mkdir()

        pm_a = ProjectMemory(ws_a)
        pm_b = ProjectMemory(ws_b)

        pm_a.append("架构与设计", "项目A使用微服务")
        pm_b.append("架构与设计", "项目B使用单体架构")

        ctx_a = pm_a.get_full_context()
        ctx_b = pm_b.get_full_context()

        assert "微服务" in ctx_a
        assert "微服务" not in ctx_b
        assert "单体架构" in ctx_b
        assert "单体架构" not in ctx_a

    def test_butler_memory_shared(self, butler_home):
        bm1 = ButlerMemory(butler_home)
        bm1.add_profile("共享偏好")

        bm2 = ButlerMemory(butler_home)
        ctx = bm2.get_system_context()
        assert "共享偏好" in ctx


class TestPostSessionProcessor:
    def test_processor_without_llm(self, butler_home, project_workspace):
        from butler.agent.post_session import PostSessionProcessor
        from butler.providers.base import Message

        messages = [
            Message.user("帮我分析一下项目的架构"),
            Message.assistant("好的，我来分析..."),
            Message.user("用事件驱动架构"),
            Message.assistant("收到，采用事件驱动架构"),
        ]

        bm = ButlerMemory(butler_home)
        pm = ProjectMemory(project_workspace)
        processor = PostSessionProcessor(llm_call=None)

        result = asyncio.run(
            processor.process(
                messages=messages,
                butler_memory=bm,
                project_memory=pm,
                project_name="test-project",
            )
        )
        assert result["memory_updates"] == 0
        assert result["skills_extracted"] == 0

    def test_processor_with_mock_llm(self, butler_home, project_workspace):
        from butler.agent.post_session import PostSessionProcessor
        from butler.providers.base import Message

        call_count = 0

        async def mock_llm(prompt: str) -> str:
            nonlocal call_count
            call_count += 1
            if "提取需要长期记住" in prompt:
                return json.dumps({"updates": [
                    {"target": "butler", "content": "喜欢详细的代码注释"},
                    {"target": "project", "section": "架构与设计", "content": "采用事件驱动架构"},
                    {"target": "experience", "content": "SQLite 在高并发下有限制"},
                ]})
            elif "可复用的操作流程" in prompt:
                return json.dumps({"skills": []})
            return json.dumps({})

        messages = [
            Message.user("帮我分析一下项目的架构，需要详细分析"),
            Message.assistant("好的，我来详细分析项目架构...这是一个比较复杂的项目..."),
            Message.user("用事件驱动架构来重构"),
            Message.assistant("收到，我建议采用事件驱动架构来重构这个系统..."),
            Message.user("SQLite 在高并发下表现如何"),
            Message.assistant("SQLite 在高并发写场景下有限制，建议考虑 PostgreSQL..."),
        ]

        bm = ButlerMemory(butler_home)
        pm = ProjectMemory(project_workspace)
        processor = PostSessionProcessor(llm_call=mock_llm)

        result = asyncio.run(
            processor.process(
                messages=messages,
                butler_memory=bm,
                project_memory=pm,
                project_name="test-project",
            )
        )

        assert isinstance(result, dict)
        assert result["memory_updates"] >= 1
        assert "喜欢详细" in bm.profile.format_for_prompt()


class TestToolDispatchEndToEnd:
    def test_project_tools(self):
        from butler.tools.registry import tool_registry
        import butler.tools.project_tools

        result = asyncio.run(
            tool_registry.dispatch("list_projects", {})
        )
        data = json.loads(result)
        assert "projects" in data

    def test_file_tools_read(self):
        import os
        from butler.tools.registry import tool_registry
        import butler.tools.file_tools

        abs_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "pyproject.toml")
        result = asyncio.run(
            tool_registry.dispatch("read_file", {"path": abs_path})
        )
        data = json.loads(result)
        assert "content" in data
        assert "butler-system" in data["content"]

    def test_memory_tools_remember_recall(self):
        from butler.tools.registry import tool_registry
        import butler.tools.memory_tools

        asyncio.run(
            tool_registry.dispatch("remember", {
                "section": "当前状态",
                "content": "集成测试进行中",
                "scope": "butler",
            })
        )
        result = asyncio.run(
            tool_registry.dispatch("recall", {"scope": "butler"})
        )
        data = json.loads(result)
        assert "butler_memory" in data or "butler_profile" in data

    def test_skill_tools_list(self):
        from butler.tools.registry import tool_registry
        import butler.tools.skill_tools

        result = asyncio.run(
            tool_registry.dispatch("skill_list", {})
        )
        data = json.loads(result)
        assert "skills" in data
        assert "count" in data

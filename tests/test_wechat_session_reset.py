"""WeChat core scenario step 6 — /new must not replay prior chat details.

Maps to docs/guides/wechat-core-scenario.md §步骤 6.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from butler.core.agent_loop import LoopStatus
from butler.gateway.message_handler import ButlerMessageHandler
from butler.session.keys import build_session_key
from butler.session.lifecycle import (
    inject_turn_memory,
    prefetch_turn_memory,
    sync_turn_memory,
)

LLM_PATCH = "butler.transport.llm_client.LLMClient"


def _text_response(content: str):
    from butler.transport.types import NormalizedResponse, Usage

    return NormalizedResponse(
        content=content,
        usage=Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
    )


@pytest.fixture
def patch_llm(mock_llm_response):
    with (
        patch(f"{LLM_PATCH}.complete") as mock_complete,
        patch(f"{LLM_PATCH}.stream") as mock_stream,
    ):
        default = mock_llm_response()
        mock_complete.return_value = default
        mock_stream.return_value = default
        yield mock_complete, mock_stream


@pytest.fixture
def gateway_handler(monkeypatch, tmp_path, tmp_butler_home):
    from tests.test_gateway_handler import _reset_singletons

    empty_projects = tmp_path / "empty-projects"
    empty_projects.mkdir()
    monkeypatch.setenv("BUTLER_PROJECTS_DIR", str(empty_projects))
    _reset_singletons()
    return ButlerMessageHandler(channel="gateway")


@pytest.mark.integration
class TestWechatCoreScenarioStep6:
    """Multi-turn chat logs → /new → ask about prior chat must not leak."""

    PLATFORM = "wechat"
    CHAT_ID = "core-step6"

    TURNS = [
        ("请读取当前项目 README 前三行并摘要", "README 介绍小说工厂流水线。"),
        (
            "请交给内容代理在 docs 写 wechat-smoke.md",
            "已委派内容代理，文件已写入 projects/LingWen/docs/wechat-smoke.md。",
        ),
        (
            "请委派开发代理检查 docs/wechat-smoke.md 是否存在",
            "开发代理确认：文件存在，共 12 行。",
        ),
    ]

    SECRET_MARKERS = ("README", "wechat-smoke", "12 行", "内容代理", "开发代理")

    def test_experience_stored_then_purged_on_new(self, gateway_handler, monkeypatch):
        monkeypatch.setenv("BUTLER_SYNC_CONVERSATION_MEMORY", "1")
        orch = gateway_handler._orchestrator
        exp = orch.butler_memory.experience
        sk = build_session_key(platform=self.PLATFORM, chat_id=self.CHAT_ID, project="")
        for user, assistant in self.TURNS:
            sync_turn_memory(
                orch,
                user,
                assistant,
                status=LoopStatus.COMPLETED,
                session_id=sk,
            )

        stored = exp.search("wechat-smoke")
        assert stored, "conversation rows should exist in DB after turns"

        cleared = gateway_handler.handle_message(
            "/新对话",
            platform=self.PLATFORM,
            external_id=self.CHAT_ID,
        )
        assert "已清空" in cleared
        assert exp.search("wechat-smoke") == []
        assert exp.search("README") == []

        after = prefetch_turn_memory(orch, "我们刚才聊过什么？")
        assert not any(m in after for m in self.SECRET_MARKERS)

        injected = inject_turn_memory(orch, "我们刚才聊过什么？")
        assert not any(m in injected for m in self.SECRET_MARKERS)

    def test_new_loop_has_no_prior_messages(self, gateway_handler, patch_llm):
        mock_complete, mock_stream = patch_llm
        sk = build_session_key(platform=self.PLATFORM, chat_id=self.CHAT_ID, project="")

        mock_complete.side_effect = [
            _text_response("好的，已读取 README。"),
            _text_response("已委派并完成。"),
            _text_response("检查完成。"),
            _text_response("上一轮对话已清空，无法复述具体细节。"),
        ]
        from tests.conftest import link_llm_stream_mock

        link_llm_stream_mock(mock_complete, mock_stream)

        for user, _ in self.TURNS:
            gateway_handler.handle_message(
                user, platform=self.PLATFORM, external_id=self.CHAT_ID
            )

        gateway_handler.handle_message(
            "/new", platform=self.PLATFORM, external_id=self.CHAT_ID
        )
        loop = gateway_handler._get_or_create_loop(sk)
        assert loop.messages == []

        out = gateway_handler.handle_message(
            "我们刚才聊过什么？",
            platform=self.PLATFORM,
            external_id=self.CHAT_ID,
        )
        assert not any(m in out for m in self.SECRET_MARKERS)

    def test_project_memory_survives_new(self, gateway_handler, patch_llm, tmp_path, monkeypatch):
        """Step 7 semantics: project context may remain; chat turns must not."""
        from tests.test_gateway_handler import _setup_projects

        _setup_projects(tmp_path, monkeypatch)
        handler = ButlerMessageHandler(channel="gateway")
        handler._orchestrator.project_manager.switch_project_for_chat(
            platform="wechat",
            chat_id="core-step7",
            name="test-project",
        )
        sk = build_session_key(platform="wechat", chat_id="core-step7", project="test-project")

        sync_turn_memory(
            handler._orchestrator,
            "请读取 wechat-only-secret-42 文件",
            "已读完。",
            status=LoopStatus.COMPLETED,
            session_id=sk,
        )
        handler.handle_message("/new", platform="wechat", external_id="core-step7")

        from butler.execution_context import use_execution_context

        with use_execution_context(handler._orchestrator, session_key=sk):
            ctx = prefetch_turn_memory(
                handler._orchestrator,
                "当前是什么项目？",
            )
        assert "wechat-only-secret-42" not in ctx
        assert (
            "test-project" in ctx
            or handler._orchestrator.project_manager.get_project_name_for_chat(
                platform="wechat", chat_id="core-step7",
            )
            == "test-project"
        )

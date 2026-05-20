"""Gateway acceptance tests mapped to docs/guides/manual-testing-guide.md §3.4–3.5.

Automated coverage for Butler-native WeChat gateway behavior. True iLink delivery
still requires manual smoke on WeChat; see §六记录表.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from butler.core.agent_loop import LoopResult, LoopStatus
from butler.gateway.message_handler import ButlerMessageHandler
from butler.gateway.platforms.types import MessageEvent, MessageType, SessionSource
from butler.gateway.runner import _butler_message_handler
from butler.tools.registry import dispatch_tool

_REPO_ROOT = Path(__file__).resolve().parent.parent
LLM_PATCH = "butler.transport.llm_client.LLMClient"


def _text_response(content: str):
    from butler.transport.types import NormalizedResponse, Usage

    return NormalizedResponse(
        content=content,
        usage=Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
    )


def _tool_response(name: str, args: dict, *, tool_id: str = "call_1"):
    from butler.transport.types import NormalizedResponse, Usage, build_tool_call

    return NormalizedResponse(
        tool_calls=[build_tool_call(tool_id, name, args)],
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
def gateway_handler():
    return ButlerMessageHandler(channel="gateway")


@pytest.fixture
def gateway_handler_with_project(tmp_path, monkeypatch, tmp_butler_home):
    from tests.test_gateway_handler import _setup_projects

    _setup_projects(tmp_path, monkeypatch)
    handler = ButlerMessageHandler(channel="gateway")
    handler._orchestrator.project_manager.switch_project("test-project")
    return handler


@pytest.mark.integration
class TestManualGuide34Dialog:
    """§3.4 微信对话"""

    def test_341_greeting(self, gateway_handler, patch_llm, mock_llm_response):
        mock_complete, mock_stream = patch_llm
        mock_complete.return_value = mock_llm_response(content="你好，我是莎丽。")
        mock_stream.return_value = mock_complete.return_value

        out = gateway_handler.handle_message("你好", session_key="wechat:u1", platform="wechat")

        assert "莎丽" in out or len(out) > 0
        assert "<think>" not in out

    def test_342_multi_turn_context(self, gateway_handler, patch_llm):
        mock_complete, mock_stream = patch_llm
        mock_complete.side_effect = [
            _text_response("好的，我记住了。"),
            _text_response("你叫王五。"),
        ]
        mock_stream.side_effect = lambda *a, **k: mock_complete.side_effect[
            min(mock_complete.call_count - 1, len(mock_complete.side_effect) - 1)
        ]

        sk = "wechat:u1"
        gateway_handler.handle_message("我叫王五", session_key=sk, platform="wechat")
        out = gateway_handler.handle_message("我叫什么？", session_key=sk, platform="wechat")

        assert "王五" in out

    def test_343_tool_read_file_line_count(self, gateway_handler, patch_llm):
        sample = _REPO_ROOT / "butler" / "gateway" / "__init__.py"
        expected = len(sample.read_text(encoding="utf-8").splitlines())
        tool_out = dispatch_tool("read_file", {"path": str(sample)})
        assert "error" not in tool_out.lower()[:80]
        assert str(expected) in tool_out or "|" in tool_out

        mock_complete, mock_stream = patch_llm
        mock_complete.side_effect = [
            _tool_response("read_file", {"path": str(sample)}),
            _text_response(f"__init__.py 共有 {expected} 行。"),
        ]
        mock_stream.side_effect = lambda *a, **k: mock_complete.side_effect[
            min(mock_complete.call_count - 1, len(mock_complete.side_effect) - 1)
        ]

        out = gateway_handler.handle_message(
            "请帮我查看 butler/gateway/__init__.py 文件有多少行",
            session_key="wechat:u1",
            platform="wechat",
        )

        assert str(expected) in out

    def test_344_wechat_truncation(self, gateway_handler):
        long_text = "行" * 3000
        result = LoopResult(status=LoopStatus.COMPLETED, final_response=long_text)
        out = gateway_handler._format_response(result, platform="wechat")
        assert len(out) <= 2000

    def test_345_media_only_prompt(self, gateway_handler, patch_llm):
        mock_complete, mock_stream = patch_llm
        mock_complete.return_value = _text_response("收到，请用文字说明需求。")
        mock_stream.return_value = mock_complete.return_value

        event = MessageEvent(
            text="",
            message_type=MessageType.PHOTO,
            source=SessionSource(platform="wechat", chat_id="u1", user_id="u1"),
            media_urls=["/tmp/fake.jpg"],
            media_types=["image/jpeg"],
        )

        async def _run():
            return await _butler_message_handler(gateway_handler, event)

        out = asyncio.run(_run())

        assert out is not None
        assert mock_complete.called
        call_args = mock_complete.call_args
        messages = call_args.kwargs.get("messages") or call_args.args[0]
        user_contents = [
            m.get("content", "")
            for m in messages
            if isinstance(m, dict) and m.get("role") == "user"
        ]
        assert any("收到媒体消息" in c for c in user_contents)

    def test_346_health_command(self, gateway_handler):
        out = gateway_handler.handle_message("/health", session_key="wechat:u1", platform="wechat")
        assert "Butler 诊断" in out or "暂无诊断" in out


@pytest.mark.integration
class TestManualGuide35Slash:
    """§3.5 微信斜杠命令"""

    @pytest.mark.parametrize(
        "cmd,needle",
        [
            ("/status", "Butler 状态"),
            ("/状态", "Butler 状态"),
            ("/model", "butler"),
            ("/模型", "butler"),
            ("/new", "已清空"),
            ("/新对话", "已清空"),
            ("/detail", "暂无"),
            ("/详细", "暂无"),
        ],
    )
    def test_slash_aliases(self, gateway_handler, cmd, needle):
        out = gateway_handler.handle_message(cmd, session_key="wechat:u1", platform="wechat")
        assert needle in out

    def test_352_projects_list(self, gateway_handler_with_project):
        out = gateway_handler_with_project.handle_message(
            "/projects", session_key="wechat:u1", platform="wechat"
        )
        assert "test-project" in out

    def test_352_projects_list_chinese_alias(self, gateway_handler_with_project):
        out = gateway_handler_with_project.handle_message(
            "/项目", session_key="wechat:u1", platform="wechat"
        )
        assert "test-project" in out

    def test_354_model_switch(self, gateway_handler):
        out = gateway_handler.handle_message(
            "/model butler minimax/MiniMax-M2.5",
            session_key="wechat:u1",
            platform="wechat",
        )
        assert "已设置" in out
        assert "MiniMax-M2.5" in out

    def test_355_switch_project(self, tmp_path, monkeypatch):
        from tests.test_gateway_handler import _setup_projects

        _setup_projects(tmp_path, monkeypatch)
        handler = ButlerMessageHandler(channel="gateway")
        out = handler.handle_message(
            "/switch test-project",
            session_key="wechat:u1",
            platform="wechat",
        )
        assert "已切换到项目" in out

    def test_356b_new_clears_chat_experience_recall(self, gateway_handler, patch_llm):
        from butler.core.agent_loop import LoopStatus
        from butler.session_lifecycle import inject_turn_memory, sync_turn_memory

        sync_turn_memory(
            gateway_handler._orchestrator,
            "请读取 wechat-smoke 文件",
            "已读取并摘要完成。",
            status=LoopStatus.COMPLETED,
            session_id="wechat:u1",
        )
        gateway_handler.handle_message("/new", session_key="wechat:u1", platform="wechat")

        augmented = inject_turn_memory(
            gateway_handler._orchestrator,
            "我们刚才聊过什么？",
        )
        assert "wechat-smoke" not in augmented

        mock_complete, mock_stream = patch_llm
        mock_complete.return_value = _text_response("上一轮对话已清空，无法复述具体细节。")
        mock_stream.return_value = mock_complete.return_value
        out = gateway_handler.handle_message(
            "我们刚才聊过什么？",
            session_key="wechat:u1",
            platform="wechat",
        )
        assert "wechat-smoke" not in out

    def test_356_new_clears_memory(self, gateway_handler, patch_llm):
        mock_complete, mock_stream = patch_llm
        mock_complete.side_effect = [
            _text_response("好的，赵六。"),
            _text_response("我不记得了。"),
        ]
        mock_stream.side_effect = lambda *a, **k: mock_complete.side_effect[
            min(mock_complete.call_count - 1, len(mock_complete.side_effect) - 1)
        ]

        sk = "wechat:u1"
        gateway_handler.handle_message("我叫赵六", session_key=sk, platform="wechat")
        gateway_handler.handle_message("/new", session_key=sk, platform="wechat")
        out = gateway_handler.handle_message("我叫什么？", session_key=sk, platform="wechat")

        assert "赵六" not in out or "不记得" in out or "不知道" in out

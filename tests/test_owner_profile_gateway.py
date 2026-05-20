"""P3: Owner profile.json is injected into gateway AgentLoop system prompt."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from butler.gateway.message_handler import ButlerMessageHandler
from butler.tenant import tenant_memory_dir

LLM_PATCH = "butler.transport.llm_client.LLMClient"


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

PROFILE_MARKER = "主公P3TEST"
STYLE_MARKER = "微信回复宜短P3MARKER"


def _write_profile(butler_home, entries: list[str]) -> None:
    mem_dir = tenant_memory_dir(butler_home, "default")
    mem_dir.mkdir(parents=True, exist_ok=True)
    path = mem_dir / "profile.json"
    path.write_text(
        json.dumps({"entries": entries}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


@pytest.mark.integration
class TestOwnerProfileGateway:
    def test_profile_entries_in_loop_system_prompt(self, tmp_butler_home):
        from tests.test_gateway_handler import _reset_singletons

        _write_profile(
            tmp_butler_home,
            [
                f"称呼：{PROFILE_MARKER}",
                f"渠道：{STYLE_MARKER}",
            ],
        )
        _reset_singletons()
        handler = ButlerMessageHandler(channel="gateway")
        loop = handler._get_or_create_loop("wechat:profile-u1")

        assert PROFILE_MARKER in loop.system_prompt
        assert STYLE_MARKER in loop.system_prompt
        assert "Owner profile" in loop.system_prompt

    def test_profile_survives_new_session_same_loop_prompt(self, tmp_butler_home):
        from tests.test_gateway_handler import _reset_singletons

        _write_profile(
            tmp_butler_home,
            [f"称呼：{PROFILE_MARKER}；回复宜短。"],
        )
        _reset_singletons()
        handler = ButlerMessageHandler(channel="gateway")

        loop_before = handler._get_or_create_loop("wechat:profile-u2")
        assert PROFILE_MARKER in loop_before.system_prompt

        handler.handle_message("/新对话", session_key="wechat:profile-u2", platform="wechat")
        loop_after = handler._get_or_create_loop("wechat:profile-u2")
        assert PROFILE_MARKER in loop_after.system_prompt

    def test_gateway_turn_user_message_not_polluted_by_profile_only_in_system(
        self, tmp_butler_home, patch_llm
    ):
        from butler.transport.types import NormalizedResponse, Usage
        from tests.test_gateway_handler import _reset_singletons

        def _text_response(content: str):
            return NormalizedResponse(
                content=content,
                usage=Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
            )

        _write_profile(tmp_butler_home, [f"称呼：{PROFILE_MARKER}"])
        _reset_singletons()
        handler = ButlerMessageHandler(channel="gateway")

        mock_complete, mock_stream = patch_llm
        mock_complete.return_value = _text_response(f"我会称呼您为{PROFILE_MARKER}。")
        mock_stream.return_value = mock_complete.return_value

        user_q = "用一句话说明你会怎么称呼我。"
        handler.handle_message(
            user_q,
            session_key="wechat:profile-u3",
            platform="wechat",
        )

        call_args = mock_complete.call_args
        messages = call_args.kwargs.get("messages") or call_args.args[0]
        system_blob = " ".join(
            str(m.get("content", ""))
            for m in messages
            if isinstance(m, dict) and m.get("role") == "system"
        )
        user_msgs = [
            str(m.get("content", ""))
            for m in messages
            if isinstance(m, dict) and m.get("role") == "user"
        ]

        assert PROFILE_MARKER in system_blob
        assert any(user_q in u for u in user_msgs)

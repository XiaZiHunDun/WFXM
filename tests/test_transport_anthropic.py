"""L2 module tests for butler.transport.anthropic_transport."""

import json
from unittest.mock import MagicMock

import pytest

from butler.transport.anthropic_transport import (
    AnthropicTransport,
    _convert_messages_to_anthropic,
    _convert_tools_to_anthropic,
)


@pytest.fixture
def transport():
    return AnthropicTransport()


@pytest.mark.module_test
class TestConvertMessagesToAnthropic:
    def test_extracts_system_messages(self):
        system, msgs = _convert_messages_to_anthropic([
            {"role": "system", "content": "You are helpful."},
            {"role": "system", "content": "Be concise."},
            {"role": "user", "content": "hi"},
        ])
        assert system == "You are helpful.\n\nBe concise."
        assert len(msgs) == 1
        assert msgs[0] == {"role": "user", "content": "hi"}

    def test_converts_user_and_assistant_text(self):
        system, msgs = _convert_messages_to_anthropic([
            {"role": "user", "content": "question"},
            {"role": "assistant", "content": "answer"},
        ])
        assert system == ""
        assert msgs[0] == {"role": "user", "content": "question"}
        assert msgs[1] == {
            "role": "assistant",
            "content": [{"type": "text", "text": "answer"}],
        }

    def test_assistant_tool_calls_to_tool_use_blocks(self):
        system, msgs = _convert_messages_to_anthropic([
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{
                    "id": "toolu_01",
                    "function": {
                        "name": "read_file",
                        "arguments": '{"path": "a.py"}',
                    },
                }],
            },
        ])
        assert system == ""
        blocks = msgs[0]["content"]
        assert blocks[0]["type"] == "tool_use"
        assert blocks[0]["id"] == "toolu_01"
        assert blocks[0]["name"] == "read_file"
        assert blocks[0]["input"] == {"path": "a.py"}

    def test_tool_role_to_tool_result_blocks(self):
        system, msgs = _convert_messages_to_anthropic([
            {
                "role": "tool",
                "tool_call_id": "toolu_01",
                "content": "file contents here",
            },
        ])
        assert system == ""
        assert msgs[0]["role"] == "user"
        block = msgs[0]["content"][0]
        assert block["type"] == "tool_result"
        assert block["tool_use_id"] == "toolu_01"
        assert block["content"] == "file contents here"


@pytest.mark.module_test
class TestConvertToolsToAnthropic:
    def test_maps_function_tools(self):
        tools = [{
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "Read a file",
                "parameters": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                },
            },
        }]
        result = _convert_tools_to_anthropic(tools)
        assert result[0]["name"] == "read_file"
        assert result[0]["description"] == "Read a file"
        assert result[0]["input_schema"]["properties"]["path"]["type"] == "string"


@pytest.mark.module_test
class TestBuildKwargs:
    def test_with_tuple_input(self, transport):
        messages_tuple = (
            "System prompt",
            [{"role": "user", "content": "hi"}],
        )
        kwargs = transport.build_kwargs(model="claude-3", messages=messages_tuple)
        assert kwargs["system"] == "System prompt"
        assert kwargs["messages"] == [{"role": "user", "content": "hi"}]

    def test_with_list_input(self, transport):
        kwargs = transport.build_kwargs(
            model="claude-3",
            messages=[
                {"role": "system", "content": "Be helpful"},
                {"role": "user", "content": "hello"},
            ],
        )
        assert kwargs["system"] == "Be helpful"
        assert kwargs["messages"] == [{"role": "user", "content": "hello"}]

    def test_includes_tools_conversion(self, transport):
        openai_tools = [{
            "type": "function",
            "function": {
                "name": "grep",
                "description": "Search files",
                "parameters": {"type": "object", "properties": {}},
            },
        }]
        kwargs = transport.build_kwargs(
            model="claude-3",
            messages=[{"role": "user", "content": "search"}],
            tools=openai_tools,
        )
        assert kwargs["tools"][0]["name"] == "grep"
        assert "input_schema" in kwargs["tools"][0]


@pytest.mark.module_test
class TestNormalizeDict:
    def test_text_blocks(self, transport):
        data = {
            "content": [{"type": "text", "text": "line one"}, {"type": "text", "text": "line two"}],
            "stop_reason": "end_turn",
        }
        resp = transport._normalize_dict(data)
        assert resp.content == "line one\nline two"
        assert resp.finish_reason == "stop"

    def test_thinking_blocks_to_reasoning(self, transport):
        data = {
            "content": [{"type": "thinking", "thinking": "let me think"}],
            "stop_reason": "end_turn",
        }
        resp = transport._normalize_dict(data)
        assert resp.reasoning == "let me think"
        assert resp.content is None

    def test_tool_use_blocks_to_tool_calls(self, transport):
        data = {
            "content": [{
                "type": "tool_use",
                "id": "toolu_abc",
                "name": "read_file",
                "input": {"path": "main.py"},
            }],
            "stop_reason": "tool_use",
        }
        resp = transport._normalize_dict(data)
        assert len(resp.tool_calls) == 1
        assert resp.tool_calls[0].name == "read_file"
        assert json.loads(resp.tool_calls[0].arguments) == {"path": "main.py"}
        assert resp.finish_reason == "tool_calls"

    @pytest.mark.parametrize(
        "stop_reason,expected",
        [
            ("end_turn", "stop"),
            ("tool_use", "tool_calls"),
            ("max_tokens", "length"),
            ("model_context_window_exceeded", "length"),
            ("stop_sequence", "stop"),
            ("refusal", "content_filter"),
        ],
    )
    def test_stop_reason_mapping(self, transport, stop_reason, expected):
        data = {"content": [], "stop_reason": stop_reason}
        resp = transport._normalize_dict(data)
        assert resp.finish_reason == expected

    def test_usage_with_input_output_tokens(self, transport):
        data = {
            "content": [{"type": "text", "text": "hi"}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 20, "output_tokens": 10},
        }
        resp = transport._normalize_dict(data)
        assert resp.usage.prompt_tokens == 20
        assert resp.usage.completion_tokens == 10
        assert resp.usage.total_tokens == 30


@pytest.mark.module_test
class TestNormalizeSdk:
    def test_sdk_response_attributes(self, transport):
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "hello"

        thinking_block = MagicMock()
        thinking_block.type = "thinking"
        thinking_block.thinking = "hmm"

        tool_block = MagicMock()
        tool_block.type = "tool_use"
        tool_block.id = "toolu_1"
        tool_block.name = "grep"
        tool_block.input = {"pattern": "foo"}

        usage = MagicMock()
        usage.input_tokens = 5
        usage.output_tokens = 3

        response = MagicMock()
        response.content = [text_block, thinking_block, tool_block]
        response.stop_reason = "tool_use"
        response.usage = usage

        resp = transport._normalize_sdk(response)
        assert resp.content == "hello"
        assert resp.reasoning == "hmm"
        assert resp.tool_calls[0].name == "grep"
        assert resp.finish_reason == "tool_calls"
        assert resp.usage.total_tokens == 8


@pytest.mark.module_test
class TestEdgeCases:
    def test_empty_content_blocks(self, transport):
        resp = transport._normalize_dict({"content": [], "stop_reason": "end_turn"})
        assert resp.content is None
        assert resp.tool_calls is None

    def test_malformed_tool_arguments_fallback(self):
        _, msgs = _convert_messages_to_anthropic([
            {
                "role": "assistant",
                "tool_calls": [{
                    "id": "toolu_bad",
                    "function": {
                        "name": "read_file",
                        "arguments": "not-valid-json{",
                    },
                }],
            },
        ])
        tool_block = msgs[0]["content"][0]
        assert tool_block["input"] == {"raw": "not-valid-json{"}

    def test_multiple_thinking_blocks_merged(self, transport):
        data = {
            "content": [
                {"type": "thinking", "thinking": "first"},
                {"type": "thinking", "thinking": "second"},
            ],
            "stop_reason": "end_turn",
        }
        resp = transport._normalize_dict(data)
        assert resp.reasoning == "first\nsecond"

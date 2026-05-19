"""L2 module tests for butler.transport.chat_completions."""

from unittest.mock import MagicMock

import pytest

from butler.transport.chat_completions import ChatCompletionsTransport


@pytest.fixture
def transport():
    return ChatCompletionsTransport()


@pytest.mark.module_test
class TestConvertMessages:
    def test_normal_messages_pass_through(self, transport):
        messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ]
        result = transport.convert_messages(messages)
        assert result == messages

    def test_strips_codex_fields(self, transport):
        messages = [
            {
                "role": "assistant",
                "content": "ok",
                "codex_reasoning_items": [{"id": "r1"}],
                "codex_message_items": [{"id": "m1"}],
            },
        ]
        result = transport.convert_messages(messages)
        assert "codex_reasoning_items" not in result[0]
        assert "codex_message_items" not in result[0]
        assert result[0]["content"] == "ok"

    def test_cleans_tool_calls(self, transport):
        messages = [
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "call-1",
                        "type": "function",
                        "function": {"name": "read_file", "arguments": "{}"},
                        "call_id": "extra-call",
                        "response_item_id": "resp-1",
                        "extra_content": {"foo": "bar"},
                    },
                ],
            },
        ]
        result = transport.convert_messages(messages)
        tc = result[0]["tool_calls"][0]
        assert tc["id"] == "call-1"
        assert "call_id" not in tc
        assert "response_item_id" not in tc
        assert "extra_content" not in tc
        assert tc["function"]["name"] == "read_file"


@pytest.mark.module_test
class TestBuildKwargs:
    def test_basic_model_and_messages(self, transport):
        kwargs = transport.build_kwargs(
            model="gpt-4o",
            messages=[{"role": "user", "content": "hi"}],
        )
        assert kwargs["model"] == "gpt-4o"
        assert kwargs["messages"] == [{"role": "user", "content": "hi"}]
        assert "tools" not in kwargs

    def test_with_tools(self, transport):
        tools = [{"type": "function", "function": {"name": "read_file"}}]
        kwargs = transport.build_kwargs(
            model="gpt-4o",
            messages=[{"role": "user", "content": "hi"}],
            tools=tools,
        )
        assert kwargs["tools"][0]["function"]["name"] == "read_file"
        assert kwargs["tools"][0]["function"]["parameters"] == {
            "type": "object",
            "properties": {},
        }

    def test_with_temperature_max_tokens_stream_timeout(self, transport):
        kwargs = transport.build_kwargs(
            model="gpt-4o",
            messages=[{"role": "user", "content": "hi"}],
            temperature=0.7,
            max_tokens=512,
            stream=True,
            timeout=60,
        )
        assert kwargs["temperature"] == 0.7
        assert kwargs["max_tokens"] == 512
        assert kwargs["stream"] is True
        assert kwargs["timeout"] == 60

    def test_with_extra_body(self, transport):
        extra = {"thinking": {"type": "enabled"}}
        kwargs = transport.build_kwargs(
            model="gpt-4o",
            messages=[{"role": "user", "content": "hi"}],
            extra_body=extra,
        )
        assert kwargs["extra_body"] == extra

    def test_sanitizes_messages_via_convert(self, transport):
        kwargs = transport.build_kwargs(
            model="gpt-4o",
            messages=[{"role": "assistant", "codex_reasoning_items": [1]}],
        )
        assert "codex_reasoning_items" not in kwargs["messages"][0]


@pytest.mark.module_test
class TestNormalizeDict:
    def test_content_only(self, transport):
        data = {
            "choices": [{"message": {"content": "hello"}, "finish_reason": "stop"}],
        }
        resp = transport._normalize_dict(data)
        assert resp.content == "hello"
        assert resp.tool_calls is None
        assert resp.finish_reason == "stop"

    def test_tool_calls_only(self, transport):
        data = {
            "choices": [{
                "message": {
                    "tool_calls": [{
                        "id": "tc-1",
                        "function": {"name": "read_file", "arguments": '{"path": "a.py"}'},
                    }],
                },
                "finish_reason": "tool_calls",
            }],
        }
        resp = transport._normalize_dict(data)
        assert resp.content is None
        assert len(resp.tool_calls) == 1
        assert resp.tool_calls[0].name == "read_file"
        assert resp.finish_reason == "tool_calls"

    def test_content_and_tool_calls(self, transport):
        data = {
            "choices": [{
                "message": {
                    "content": "calling tool",
                    "tool_calls": [{
                        "id": "tc-1",
                        "function": {"name": "run_shell", "arguments": "{}"},
                    }],
                },
                "finish_reason": "tool_calls",
            }],
        }
        resp = transport._normalize_dict(data)
        assert resp.content == "calling tool"
        assert resp.tool_calls[0].name == "run_shell"

    def test_empty_choices_returns_error(self, transport):
        resp = transport._normalize_dict({"choices": []})
        assert resp.finish_reason == "error"

    def test_with_reasoning_field(self, transport):
        data = {
            "choices": [{
                "message": {"content": "answer", "reasoning": "step by step"},
                "finish_reason": "stop",
            }],
        }
        resp = transport._normalize_dict(data)
        assert resp.reasoning == "step by step"

    def test_with_reasoning_content_field(self, transport):
        data = {
            "choices": [{
                "message": {"content": "answer", "reasoning_content": "chain"},
                "finish_reason": "stop",
            }],
        }
        resp = transport._normalize_dict(data)
        assert resp.reasoning == "chain"

    def test_usage_extraction(self, transport):
        data = {
            "choices": [{"message": {"content": "x"}, "finish_reason": "stop"}],
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 50,
                "total_tokens": 150,
            },
        }
        resp = transport._normalize_dict(data)
        assert resp.usage.prompt_tokens == 100
        assert resp.usage.completion_tokens == 50
        assert resp.usage.total_tokens == 150


@pytest.mark.module_test
class TestNormalizeSdk:
    def test_sdk_response_attributes(self, transport):
        fn = MagicMock()
        fn.name = "read_file"
        fn.arguments = '{"path": "main.py"}'

        tc = MagicMock()
        tc.id = "call-1"
        tc.function = fn

        msg = MagicMock()
        msg.content = "done"
        msg.reasoning = "thought"
        msg.tool_calls = [tc]

        choice = MagicMock()
        choice.message = msg
        choice.finish_reason = "tool_calls"

        usage = MagicMock()
        usage.prompt_tokens = 10
        usage.completion_tokens = 5
        usage.total_tokens = 15

        response = MagicMock()
        response.choices = [choice]
        response.usage = usage

        resp = transport._normalize_sdk(response)
        assert resp.content == "done"
        assert resp.reasoning == "thought"
        assert resp.tool_calls[0].name == "read_file"
        assert resp.finish_reason == "tool_calls"
        assert resp.usage.total_tokens == 15


@pytest.mark.module_test
class TestValidateResponse:
    def test_dict_with_choices_true(self, transport):
        assert transport.validate_response({"choices": [{"message": {}}]}) is True

    def test_dict_without_choices_false(self, transport):
        assert transport.validate_response({"choices": []}) is False
        assert transport.validate_response({}) is False

    def test_sdk_with_choices_true(self, transport):
        response = MagicMock()
        response.choices = [MagicMock()]
        assert transport.validate_response(response) is True

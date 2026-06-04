"""L2 module tests for butler.transport.llm_client."""

from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from butler.transport.llm_client import LLMClient
from butler.transport.providers import ProviderProfile
from butler.transport.types import NormalizedResponse, ToolCall


@pytest.mark.module_test
class TestResolveConfig:
    def test_provider_uses_profile_defaults(self, monkeypatch):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
        client = LLMClient(provider="deepseek")
        assert client._base_url == "https://api.deepseek.com/v1"
        assert client._api_key == "sk-test"
        assert client.model == "deepseek-chat"
        assert client.api_mode == "chat_completions"

    def test_explicit_override_wins(self, monkeypatch):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-env")
        client = LLMClient(
            provider="deepseek",
            model="custom-model",
            api_key="sk-override",
            base_url="https://custom.example/v1",
            api_mode="anthropic_messages",
        )
        assert client.model == "custom-model"
        assert client._api_key == "sk-override"
        assert client._base_url == "https://custom.example/v1"
        assert client.api_mode == "anthropic_messages"

    def test_no_provider_detects_api_mode_from_url(self):
        client = LLMClient(
            base_url="https://api.example.com/anthropic",
            model="test-model",
        )
        assert client.api_mode == "anthropic_messages"

    def test_no_provider_non_anthropic_url(self):
        client = LLMClient(
            base_url="https://api.example.com/v1",
            model="test-model",
        )
        assert client.api_mode == "chat_completions"


@pytest.mark.module_test
class TestDetectApiMode:
    def test_url_ending_anthropic(self):
        client = LLMClient(base_url="https://api.minimax.chat/anthropic")
        assert client._detect_api_mode() == "anthropic_messages"

    def test_other_url_chat_completions(self):
        client = LLMClient(base_url="https://api.openai.com/v1")
        assert client._detect_api_mode() == "chat_completions"


@pytest.mark.module_test
class TestApiModeProperty:
    def test_returns_configured_mode(self):
        client = LLMClient(api_mode="anthropic_messages", model="m")
        assert client.api_mode == "anthropic_messages"

    def test_defaults_to_chat_completions(self):
        client = LLMClient(model="m")
        assert client.api_mode == "chat_completions"


@pytest.mark.module_test
class TestCompleteChatCompletions:
    @patch("butler.transport.llm_client.LLMClient._get_openai_client")
    def test_calls_transport_build_and_normalize(self, mock_get_client):
        mock_client = MagicMock(# noqa: magicmock-no-spec — LLM client OpenAI/Anthropic stream chunk / facade
)
        mock_get_client.return_value = mock_client
        mock_client.chat.completions.create.return_value = {
            "choices": [{
                "message": {"content": "hello"},
                "finish_reason": "stop",
            }],
        }

        client = LLMClient(
            api_mode="chat_completions",
            model="gpt-4o",
            base_url="https://api.example.com/v1",
        )
        result = client.complete(
            messages=[{"role": "user", "content": "hi"}],
            temperature=0.5,
        )

        mock_client.chat.completions.create.assert_called_once()
        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert call_kwargs["model"] == "gpt-4o"
        assert call_kwargs["messages"] == [{"role": "user", "content": "hi"}]
        assert call_kwargs["temperature"] == 0.5
        assert result.content == "hello"
        assert result.finish_reason == "stop"


@pytest.mark.module_test
class TestCompleteAnthropic:
    @patch("butler.transport.llm_client.LLMClient._get_anthropic_client")
    def test_messages_create_called(self, mock_get_client):
        mock_client = MagicMock(# noqa: magicmock-no-spec — LLM client OpenAI/Anthropic stream chunk / facade
)
        mock_get_client.return_value = mock_client
        mock_client.messages.create.return_value = {
            "content": [{"type": "text", "text": "anthropic reply"}],
            "stop_reason": "end_turn",
        }

        client = LLMClient(
            api_mode="anthropic_messages",
            model="claude-sonnet",
            base_url="https://api.anthropic.com",
        )
        result = client.complete(
            messages=[{"role": "user", "content": "hi"}],
        )

        mock_client.messages.create.assert_called_once()
        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert call_kwargs["model"] == "claude-sonnet"
        assert result.content == "anthropic reply"
        assert result.finish_reason == "stop"


@pytest.mark.module_test
class TestStreamChatCompletions:
    @patch("butler.transport.llm_client.LLMClient._get_openai_client")
    def test_assembles_content_and_tool_calls(self, mock_get_client):
        chunk1 = MagicMock(# noqa: magicmock-no-spec — LLM client OpenAI/Anthropic stream chunk / facade
)
        chunk1.choices = [MagicMock()]  # noqa: magicmock-no-spec — LLM client OpenAI/Anthropic stream chunk / facade
        chunk1.choices[0].delta = MagicMock(# noqa: magicmock-no-spec — LLM client OpenAI/Anthropic stream chunk / facade
content="Hel", tool_calls=None)
        chunk1.choices[0].finish_reason = None

        fn_delta = MagicMock(# noqa: magicmock-no-spec — LLM client OpenAI/Anthropic stream chunk / facade
)
        fn_delta.name = "read_file"
        fn_delta.arguments = '{"path":'

        tc_delta = MagicMock(# noqa: magicmock-no-spec — LLM client OpenAI/Anthropic stream chunk / facade
)
        tc_delta.index = 0
        tc_delta.id = "call-1"
        tc_delta.function = fn_delta

        chunk2 = MagicMock(# noqa: magicmock-no-spec — LLM client OpenAI/Anthropic stream chunk / facade
)
        chunk2.choices = [MagicMock()]  # noqa: magicmock-no-spec — LLM client OpenAI/Anthropic stream chunk / facade
        chunk2.choices[0].delta = MagicMock(# noqa: magicmock-no-spec — LLM client OpenAI/Anthropic stream chunk / facade
content="lo", tool_calls=[tc_delta])
        chunk2.choices[0].finish_reason = None

        fn_delta2 = MagicMock(# noqa: magicmock-no-spec — LLM client OpenAI/Anthropic stream chunk / facade
)
        fn_delta2.name = None
        fn_delta2.arguments = ' "a.py"}'

        tc_delta2 = MagicMock(# noqa: magicmock-no-spec — LLM client OpenAI/Anthropic stream chunk / facade
)
        tc_delta2.index = 0
        tc_delta2.id = None
        tc_delta2.function = fn_delta2

        chunk3 = MagicMock(# noqa: magicmock-no-spec — LLM client OpenAI/Anthropic stream chunk / facade
)
        chunk3.choices = [MagicMock()]  # noqa: magicmock-no-spec — LLM client OpenAI/Anthropic stream chunk / facade
        chunk3.choices[0].delta = MagicMock(# noqa: magicmock-no-spec — LLM client OpenAI/Anthropic stream chunk / facade
content=None, tool_calls=[tc_delta2])
        chunk3.choices[0].finish_reason = "tool_calls"

        mock_client = MagicMock(# noqa: magicmock-no-spec — LLM client OpenAI/Anthropic stream chunk / facade
)
        mock_get_client.return_value = mock_client
        mock_client.chat.completions.create.return_value = iter([chunk1, chunk2, chunk3])

        client = LLMClient(api_mode="chat_completions", model="gpt-4o")
        result = client.stream(messages=[{"role": "user", "content": "hi"}])

        assert result.content == "Hello"
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].name == "read_file"
        assert result.tool_calls[0].arguments == '{"path": "a.py"}'
        assert result.finish_reason == "tool_calls"


@pytest.mark.module_test
class TestStreamAnthropic:
    @patch("butler.transport.llm_client.LLMClient._get_anthropic_client")
    def test_messages_stream_events(self, mock_get_client):
        tool_block = SimpleNamespace(type="tool_use", id="toolu_1", name="grep")
        block_start = SimpleNamespace(
            type="content_block_start",
            content_block=tool_block,
        )

        text_delta = SimpleNamespace(
            type="content_block_delta",
            delta=SimpleNamespace(type="text_delta", text="Hi "),
        )

        json_delta = SimpleNamespace(
            type="content_block_delta",
            delta=SimpleNamespace(
                type="input_json_delta",
                partial_json='{"pattern": "x"}',
            ),
        )

        block_stop = SimpleNamespace(type="content_block_stop")

        msg_delta = SimpleNamespace(
            type="message_delta",
            delta=SimpleNamespace(stop_reason="end_turn"),
            usage=SimpleNamespace(input_tokens=10, output_tokens=5),
        )

        mock_stream = MagicMock(# noqa: magicmock-no-spec — LLM client OpenAI/Anthropic stream chunk / facade
)
        mock_stream.__iter__ = MagicMock(# noqa: magicmock-no-spec — LLM client OpenAI/Anthropic stream chunk / facade

            return_value=iter([block_start, text_delta, json_delta, block_stop, msg_delta])
        )

        @contextmanager
        def fake_stream(**kwargs):
            yield mock_stream

        mock_client = MagicMock(# noqa: magicmock-no-spec — LLM client OpenAI/Anthropic stream chunk / facade
)
        mock_client.messages = MagicMock(# noqa: magicmock-no-spec — LLM client OpenAI/Anthropic stream chunk / facade
)
        mock_client.messages.stream = fake_stream
        mock_get_client.return_value = mock_client

        client = LLMClient(api_mode="anthropic_messages", model="claude-3")
        result = client.stream(messages=[{"role": "user", "content": "search"}])

        assert result.content == "Hi "
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].name == "grep"
        assert result.tool_calls[0].arguments == '{"pattern": "x"}'
        assert result.finish_reason == "stop"
        assert result.usage.total_tokens == 15


@pytest.mark.module_test
class TestGetOpenaiClient:
    def test_import_error_raises_runtime_error(self):
        client = LLMClient(api_mode="chat_completions", model="m")
        with patch.dict("sys.modules", {"openai": None}):
            with patch(
                "builtins.__import__",
                side_effect=lambda name, *a, **kw: (_ for _ in ()).throw(
                    ImportError("no openai")
                ) if name == "openai" else __import__(name, *a, **kw),
            ):
                with pytest.raises(RuntimeError, match="openai package required"):
                    client._get_openai_client()


@pytest.mark.module_test
class TestGetAnthropicClient:
    def test_import_error_falls_back_to_openai(self):
        client = LLMClient(api_mode="anthropic_messages", model="m")
        mock_openai_cls = MagicMock(# noqa: magicmock-no-spec — LLM client OpenAI/Anthropic stream chunk / facade
)
        mock_openai_instance = MagicMock(# noqa: magicmock-no-spec — LLM client OpenAI/Anthropic stream chunk / facade
)
        mock_openai_cls.return_value = mock_openai_instance

        import builtins
        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "anthropic":
                raise ImportError("no anthropic")
            if name == "openai":
                return MagicMock(OpenAI=mock_openai_cls)  # noqa: magicmock-no-spec — fake import shim returning module-like mock
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=fake_import):
            result = client._get_anthropic_client()

        assert result is mock_openai_instance
        assert client.api_mode == "chat_completions"


@pytest.mark.module_test
class TestStreamErrorHandling:
    @patch("butler.transport.llm_client.LLMClient._get_openai_client")
    def test_partial_content_on_stream_error(self, mock_get_client):
        chunk = MagicMock(# noqa: magicmock-no-spec — LLM client OpenAI/Anthropic stream chunk / facade
)
        chunk.choices = [MagicMock()]  # noqa: magicmock-no-spec — LLM client OpenAI/Anthropic stream chunk / facade
        chunk.choices[0].delta = MagicMock(# noqa: magicmock-no-spec — LLM client OpenAI/Anthropic stream chunk / facade
content="partial", tool_calls=None)
        chunk.choices[0].finish_reason = None

        mock_client = MagicMock(# noqa: magicmock-no-spec — LLM client OpenAI/Anthropic stream chunk / facade
)
        mock_get_client.return_value = mock_client

        def failing_stream(**kwargs):
            yield chunk
            raise RuntimeError("connection lost")

        mock_client.chat.completions.create.side_effect = failing_stream

        client = LLMClient(api_mode="chat_completions", model="gpt-4o")
        result = client.stream(messages=[{"role": "user", "content": "hi"}])
        assert result.content == "partial"


@pytest.mark.module_test
class TestTimeoutPassing:
    @patch("butler.transport.llm_client.LLMClient._get_openai_client")
    def test_timeout_in_build_kwargs(self, mock_get_client):
        mock_client = MagicMock(# noqa: magicmock-no-spec — LLM client OpenAI/Anthropic stream chunk / facade
)
        mock_get_client.return_value = mock_client
        mock_client.chat.completions.create.return_value = {
            "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
        }

        client = LLMClient(
            api_mode="chat_completions",
            model="gpt-4o",
            timeout=45,
        )
        client.complete(messages=[{"role": "user", "content": "hi"}], timeout=90)

        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert call_kwargs["timeout"] == 90

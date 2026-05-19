"""Sprint E: domestic model hardening (reasoning replay, JSON repair, stream scrubber)."""

import json
from types import SimpleNamespace

from butler.core.json_repair import repair_tool_call_arguments
from butler.core.message_repair import repair_tool_arguments
from butler.transport.chat_completions import ChatCompletionsTransport
from butler.transport.llm_client import LLMClient
from butler.transport.reasoning_replay import (
    apply_reasoning_for_api,
    needs_deepseek_tool_reasoning,
    needs_kimi_tool_reasoning,
    needs_thinking_reasoning_pad,
)
from butler.transport.think_scrubber import StreamingThinkScrubber


class TestReasoningReplay:
    def test_deepseek_detection(self):
        assert needs_deepseek_tool_reasoning("deepseek", "deepseek-chat")
        assert needs_deepseek_tool_reasoning("", "", "https://api.deepseek.com/v1")

    def test_kimi_detection(self):
        assert needs_kimi_tool_reasoning("kimi-coding", "")
        assert needs_kimi_tool_reasoning("", "", "https://api.moonshot.cn/v1")

    def test_pad_tool_call_without_reasoning(self):
        src = {
            "role": "assistant",
            "content": None,
            "tool_calls": [{"id": "1", "type": "function", "function": {"name": "x", "arguments": "{}"}}],
        }
        api = dict(src)
        apply_reasoning_for_api(src, api, provider="deepseek", model="deepseek-chat")
        assert api["reasoning_content"] == " "

    def test_preserve_explicit_reasoning(self):
        src = {
            "role": "assistant",
            "content": "ok",
            "reasoning_content": "chain",
        }
        api = dict(src)
        apply_reasoning_for_api(src, api, provider="deepseek")
        assert api["reasoning_content"] == "chain"

    def test_empty_reasoning_upgraded_for_deepseek(self):
        src = {"role": "assistant", "content": "hi", "reasoning_content": ""}
        api = dict(src)
        apply_reasoning_for_api(src, api, provider="deepseek", model="deepseek-reasoner")
        assert api["reasoning_content"] == " "

    def test_cross_provider_poison_block(self):
        src = {
            "role": "assistant",
            "reasoning": "minimax thought",
            "tool_calls": [{"id": "1"}],
        }
        api = dict(src)
        apply_reasoning_for_api(src, api, provider="deepseek")
        assert api["reasoning_content"] == " "

    def test_convert_messages_injects_pad(self):
        t = ChatCompletionsTransport()
        msgs = [
            {
                "role": "assistant",
                "tool_calls": [
                    {"id": "c1", "type": "function", "function": {"name": "t", "arguments": "{}"}},
                ],
            },
        ]
        out = t.convert_messages(msgs, provider="deepseek", model="deepseek-chat")
        assert out[0]["reasoning_content"] == " "

    def test_convert_messages_strips_internal_reasoning(self):
        t = ChatCompletionsTransport()
        out = t.convert_messages(
            [{"role": "assistant", "content": "ok", "reasoning": "internal"}],
            provider="deepseek",
            model="deepseek-chat",
        )
        assert "reasoning" not in out[0]
        assert out[0]["reasoning_content"] == "internal"

    def test_no_pad_for_openai(self):
        assert not needs_thinking_reasoning_pad("openai", "gpt-4o")


class TestJsonRepair:
    def test_trailing_comma(self):
        fixed = repair_tool_call_arguments('{"a": 1,}', tool_name="t")
        assert json.loads(fixed) == {"a": 1}

    def test_unclosed_brace(self):
        fixed = repair_tool_call_arguments('{"a": 1', tool_name="t")
        assert json.loads(fixed)["a"] == 1

    def test_python_none(self):
        assert repair_tool_call_arguments("None") == "{}"

    def test_repair_tool_arguments_integration(self):
        msgs = [
            {
                "role": "assistant",
                "tool_calls": [
                    {"function": {"name": "x", "arguments": '{"k": 1,}'}},
                ],
            },
        ]
        n = repair_tool_arguments(msgs)
        assert n >= 1
        assert json.loads(msgs[0]["tool_calls"][0]["function"]["arguments"])["k"] == 1


class TestStreamingThinkScrubber:
    def test_split_tag_across_deltas(self):
        s = StreamingThinkScrubber()
        assert s.feed("<think>") == ""
        assert s.feed("secret") == ""
        assert s.feed("</think>") == ""
        assert s.feed("Hello") == "Hello"

    def test_closed_pair_inline(self):
        s = StreamingThinkScrubber()
        out = s.feed("before<thinking>x</thinking>after")
        assert "x" not in out
        assert "before" in out and "after" in out

    def test_reset_between_turns(self):
        s = StreamingThinkScrubber()
        s.feed("<thinking>partial")
        s.reset()
        assert s.feed("visible") == "visible"

    def test_flush_emits_held_partial(self):
        s = StreamingThinkScrubber()
        s.feed("hello <thi")
        assert s.flush() == "<thi"


class TestStreamingReasoningCollection:
    def test_stream_call_collects_reasoning_delta(self):
        chunk = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    delta=SimpleNamespace(content="answer", reasoning_content="thought"),
                    finish_reason="stop",
                )
            ],
            usage=None,
        )
        fake_client = SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(create=lambda **_: [chunk])
            )
        )
        client = LLMClient(model="m")
        client._get_openai_client = lambda: fake_client

        response = client._stream_call({"model": "m", "messages": []})

        assert response.content == "answer"
        assert response.reasoning == "thought"

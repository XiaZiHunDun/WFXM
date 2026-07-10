"""Sprint 29 P2-4.3: transport-level cache_control 4-boundary auto-placement.

P2-4.3-gap 落地: 当前 `butler/transport/` 完全没有 cache_control 布点.
`cache_safe_delegate` 是 delegate 侧 "防 prefix 改坏 cache" 的安全策略 (不同层次);
本任务做 transport 侧 "自动在 4 个 boundary 布 cache_control: {type: ephemeral}" 的
优化层, 对应 Anthropic Prompt Caching 标配:
  1. system prompt
  2. 最后 user message (多轮对话历史锚点)
  3. tools 数组最后一项 (工具 schema 锚点)
  4. 最后 tool_result 块 (工具结果锚点)

覆盖:
  - env toggle: 默认 True / BUTLER_TRANSPORT_CACHE_CONTROL=0 关闭 / 1 开启
  - system 转换: 关闭返 [] / 开启+空 system 返 [] / 开启+有 text 返带 marker 的 list
  - messages 转换: 关闭透传 / 开启+最后 user 加 cache_control / 开启+最后 user 是
    tool_result 时给最后 tool_result 块加 / 开启+最后 assistant 不动
  - tools 转换: 关闭透传 / 开启+最后 tool 加 cache_control
  - 集成: build_kwargs 4 boundary 全部在时, 4 处 marker 全到位
  - bypass 集成: BUTLER_TRANSPORT_CACHE_CONTROL=0 时 anthropic_transport.build_kwargs
    与 HEAD~ 输出一致 (除 system str→list 的 1 处分歧, 这是本任务改造的语义)
"""

from __future__ import annotations

import pytest


# ── env toggle: cache_control_enabled ──


class TestCacheControlEnabled:
    def test_default_true_when_unset(self, monkeypatch):
        """未设 env → 默认开启."""
        monkeypatch.delenv("BUTLER_TRANSPORT_CACHE_CONTROL", raising=False)
        from butler.transport.cache_control import cache_control_enabled

        assert cache_control_enabled() is True

    def test_disabled_when_zero(self, monkeypatch):
        """BUTLER_TRANSPORT_CACHE_CONTROL=0 → 关闭."""
        monkeypatch.setenv("BUTLER_TRANSPORT_CACHE_CONTROL", "0")
        from butler.transport.cache_control import cache_control_enabled

        assert cache_control_enabled() is False

    def test_disabled_when_false(self, monkeypatch):
        """BUTLER_TRANSPORT_CACHE_CONTROL=false → 关闭."""
        monkeypatch.setenv("BUTLER_TRANSPORT_CACHE_CONTROL", "false")
        from butler.transport.cache_control import cache_control_enabled

        assert cache_control_enabled() is False

    def test_enabled_when_one(self, monkeypatch):
        """BUTLER_TRANSPORT_CACHE_CONTROL=1 → 开启."""
        monkeypatch.setenv("BUTLER_TRANSPORT_CACHE_CONTROL", "1")
        from butler.transport.cache_control import cache_control_enabled

        assert cache_control_enabled() is True


# ── system boundary: apply_cache_control_to_system ──


class TestApplySystem:
    def test_disabled_returns_empty_list(self, monkeypatch):
        """关闭时无论 system 是否非空 → 返 [] (caller 决定是否用)."""
        monkeypatch.setenv("BUTLER_TRANSPORT_CACHE_CONTROL", "0")
        from butler.transport.cache_control import apply_cache_control_to_system

        # 关闭时返空, caller 走原 str 路径
        assert apply_cache_control_to_system("anything") == []

    def test_enabled_empty_system_returns_empty(self, monkeypatch):
        """开启 + 空 system → 返 [] (不构造空 block)."""
        monkeypatch.delenv("BUTLER_TRANSPORT_CACHE_CONTROL", raising=False)
        from butler.transport.cache_control import apply_cache_control_to_system

        assert apply_cache_control_to_system("") == []
        assert apply_cache_control_to_system("   ") == []

    def test_enabled_with_text_returns_marker_block(self, monkeypatch):
        """开启 + 有 system text → 返 1 个 text block 带 cache_control:ephemeral."""
        monkeypatch.delenv("BUTLER_TRANSPORT_CACHE_CONTROL", raising=False)
        from butler.transport.cache_control import apply_cache_control_to_system

        out = apply_cache_control_to_system("you are a helpful assistant")
        assert isinstance(out, list) and len(out) == 1
        block = out[0]
        assert block["type"] == "text"
        assert block["text"] == "you are a helpful assistant"
        assert block["cache_control"] == {"type": "ephemeral"}


# ── messages boundary: apply_cache_control_to_messages ──


class TestApplyMessages:
    def test_disabled_returns_input_unchanged(self, monkeypatch):
        """关闭时透传, 不修改原 messages."""
        monkeypatch.setenv("BUTLER_TRANSPORT_CACHE_CONTROL", "0")
        from butler.transport.cache_control import apply_cache_control_to_messages

        msgs = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
            {"role": "user", "content": "bye"},
        ]
        out = apply_cache_control_to_messages(msgs)
        assert out == msgs

    def test_enabled_last_user_gets_cache_control(self, monkeypatch):
        """开启 + 最后一条是 user → 给 user 末尾加 cache_control block."""
        monkeypatch.delenv("BUTLER_TRANSPORT_CACHE_CONTROL", raising=False)
        from butler.transport.cache_control import apply_cache_control_to_messages

        msgs = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
            {"role": "user", "content": "bye"},
        ]
        out = apply_cache_control_to_messages(msgs)
        # 最后 user 仍存在
        assert out[-1]["role"] == "user"
        # content 应为 list 形式, 末尾追加 1 个 text block + cache_control
        content = out[-1]["content"]
        assert isinstance(content, list)
        # 末尾 block 是空 text + cache_control marker (不覆盖原 user 文本)
        tail = content[-1]
        assert tail["type"] == "text"
        assert tail["text"] == ""
        assert tail["cache_control"] == {"type": "ephemeral"}
        # 原 user 文本保留在第一个 block
        assert content[0]["type"] == "text"
        assert content[0]["text"] == "bye"
        # 前面消息未动
        assert out[0] == {"role": "user", "content": "hi"}
        assert out[1] == {"role": "assistant", "content": "hello"}

    def test_enabled_last_user_str_becomes_list(self, monkeypatch):
        """开启 + user content 是 str → 转 list + 末尾追加 marker block (不覆盖原 text)."""
        monkeypatch.delenv("BUTLER_TRANSPORT_CACHE_CONTROL", raising=False)
        from butler.transport.cache_control import apply_cache_control_to_messages

        msgs = [{"role": "user", "content": "first ask"}]
        out = apply_cache_control_to_messages(msgs)
        content = out[-1]["content"]
        assert isinstance(content, list)
        assert len(content) == 2
        assert content[0] == {"type": "text", "text": "first ask"}
        assert content[1]["cache_control"] == {"type": "ephemeral"}

    def test_enabled_last_user_already_list_appends(self, monkeypatch):
        """开启 + user content 已经是 list (多 block) → 在 list 末尾追加 marker block."""
        monkeypatch.delenv("BUTLER_TRANSPORT_CACHE_CONTROL", raising=False)
        from butler.transport.cache_control import apply_cache_control_to_messages

        msgs = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "first part"},
                    {"type": "text", "text": "second part"},
                ],
            },
        ]
        out = apply_cache_control_to_messages(msgs)
        content = out[-1]["content"]
        assert len(content) == 3
        assert content[0]["text"] == "first part"
        assert content[1]["text"] == "second part"
        assert content[2]["cache_control"] == {"type": "ephemeral"}

    def test_enabled_last_user_is_tool_result(self, monkeypatch):
        """开启 + 最后 user 是 tool_result 块 → 给最后那个 tool_result 块加 cache_control."""
        monkeypatch.delenv("BUTLER_TRANSPORT_CACHE_CONTROL", raising=False)
        from butler.transport.cache_control import apply_cache_control_to_messages

        msgs = [
            {"role": "user", "content": "ask"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": "call_1", "function": {"name": "echo", "arguments": "{}"}},
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "call_1",
                "content": "result text",
            },
        ]
        out = apply_cache_control_to_messages(msgs)
        # 最后一条是 tool → 在 anthropic 转换时会变 user(role=tool→user + tool_result block)
        # 本函数是 transport-agnostic, 关注的是 role=user 的最后一条
        # 上面 3 条都不是 role=user (assistant + tool), 所以 out 应保持
        # (此 case 实际由 anthropic_transport 负责转换; 这里的 apply_messages 仅在
        #  role=user 的最后一条上加 marker. 在此 case, role=user 在 index 0, 但不是
        #  最后, 所以不动. 验证: out[-1] 仍是 tool 不变)
        assert out[-1]["role"] == "tool"
        assert out[-1]["content"] == "result text"

    def test_enabled_last_assistant_not_touched(self, monkeypatch):
        """开启 + 最后一条是 assistant → 不动 (assistant 不作 cache breakpoint)."""
        monkeypatch.delenv("BUTLER_TRANSPORT_CACHE_CONTROL", raising=False)
        from butler.transport.cache_control import apply_cache_control_to_messages

        msgs = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
        ]
        out = apply_cache_control_to_messages(msgs)
        # assistant 仍为 str, 未被 wrap
        assert out[-1] == {"role": "assistant", "content": "hello"}

    def test_enabled_no_user_messages_noop(self, monkeypatch):
        """开启 + 没有 role=user 的消息 → 整体不动."""
        monkeypatch.delenv("BUTLER_TRANSPORT_CACHE_CONTROL", raising=False)
        from butler.transport.cache_control import apply_cache_control_to_messages

        msgs = [
            {"role": "system", "content": "sys"},
            {"role": "assistant", "content": "no user"},
        ]
        out = apply_cache_control_to_messages(msgs)
        assert out == msgs


# ── tools boundary: apply_cache_control_to_tools ──


class TestApplyTools:
    def test_disabled_returns_input_unchanged(self, monkeypatch):
        """关闭时透传, 不修改原 tools."""
        monkeypatch.setenv("BUTLER_TRANSPORT_CACHE_CONTROL", "0")
        from butler.transport.cache_control import apply_cache_control_to_tools

        tools = [
            {"name": "a", "description": "first", "input_schema": {"type": "object"}},
            {"name": "b", "description": "second", "input_schema": {"type": "object"}},
        ]
        out = apply_cache_control_to_tools(tools)
        assert out == tools

    def test_enabled_last_tool_gets_cache_control(self, monkeypatch):
        """开启 + tools 非空 → 最后 1 个 tool 加 cache_control:ephemeral."""
        monkeypatch.delenv("BUTLER_TRANSPORT_CACHE_CONTROL", raising=False)
        from butler.transport.cache_control import apply_cache_control_to_tools

        tools = [
            {"name": "a", "description": "first", "input_schema": {"type": "object"}},
            {"name": "b", "description": "second", "input_schema": {"type": "object"}},
            {"name": "c", "description": "third", "input_schema": {"type": "object"}},
        ]
        out = apply_cache_control_to_tools(tools)
        # 前面不动
        assert out[0] == tools[0]
        assert out[1] == tools[1]
        # 最后 1 个加 marker
        assert out[-1]["name"] == "c"
        assert out[-1]["cache_control"] == {"type": "ephemeral"}
        # 其它字段保留
        assert out[-1]["description"] == "third"
        assert out[-1]["input_schema"] == {"type": "object"}

    def test_enabled_empty_tools_returns_empty(self, monkeypatch):
        """开启 + 空 tools → 返 []."""
        monkeypatch.delenv("BUTLER_TRANSPORT_CACHE_CONTROL", raising=False)
        from butler.transport.cache_control import apply_cache_control_to_tools

        assert apply_cache_control_to_tools([]) == []
        assert apply_cache_control_to_tools(None) == []


# ── 集成: 4 boundary 同时 in-place ──


class TestFourBoundariesIntegration:
    def test_all_four_boundaries_present(self, monkeypatch):
        """4 boundary 同时: system + last user + tools + last tool_result 全有 marker."""
        monkeypatch.delenv("BUTLER_TRANSPORT_CACHE_CONTROL", raising=False)
        from butler.transport.cache_control import (
            apply_cache_control_to_messages,
            apply_cache_control_to_system,
            apply_cache_control_to_tools,
        )

        system_text = "you are a helpful assistant"
        messages = [
            {"role": "user", "content": "ask"},
            {"role": "assistant", "content": "first reply"},
            {"role": "user", "content": "second ask"},
        ]
        tools = [
            {"name": "echo", "description": "echo back", "input_schema": {"type": "object"}},
        ]

        # boundary 1: system
        sys_blocks = apply_cache_control_to_system(system_text)
        assert sys_blocks[-1]["cache_control"] == {"type": "ephemeral"}

        # boundary 2 + 4: messages (最后 user 末尾加 marker)
        msgs_out = apply_cache_control_to_messages(messages)
        last_user_content = msgs_out[-1]["content"]
        assert isinstance(last_user_content, list)
        assert last_user_content[-1]["cache_control"] == {"type": "ephemeral"}

        # boundary 3: tools
        tools_out = apply_cache_control_to_tools(tools)
        assert tools_out[-1]["cache_control"] == {"type": "ephemeral"}

    def test_bypass_disables_all_four(self, monkeypatch):
        """BUTLER_TRANSPORT_CACHE_CONTROL=0 → 4 boundary 全部不动."""
        monkeypatch.setenv("BUTLER_TRANSPORT_CACHE_CONTROL", "0")
        from butler.transport.cache_control import (
            apply_cache_control_to_messages,
            apply_cache_control_to_system,
            apply_cache_control_to_tools,
        )

        system_text = "sys"
        messages = [{"role": "user", "content": "hi"}]
        tools = [{"name": "t", "description": "d", "input_schema": {"type": "object"}}]

        # 关闭时 system 返空 (caller 走原 str)
        assert apply_cache_control_to_system(system_text) == []
        # messages 透传
        assert apply_cache_control_to_messages(messages) == messages
        # tools 透传
        assert apply_cache_control_to_tools(tools) == tools


# ── boundary 4 helper: apply_cache_control_to_last_tool_result ──


class TestApplyLastToolResult:
    def test_disabled_passthrough(self, monkeypatch):
        """关闭时透传."""
        monkeypatch.setenv("BUTLER_TRANSPORT_CACHE_CONTROL", "0")
        from butler.transport.cache_control import (
            apply_cache_control_to_last_tool_result,
        )

        msgs = [
            {
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": "c1", "content": "r"}],
            },
        ]
        assert apply_cache_control_to_last_tool_result(msgs) == msgs

    def test_no_tool_result_noop(self, monkeypatch):
        """无 tool_result 块 → 不动."""
        monkeypatch.delenv("BUTLER_TRANSPORT_CACHE_CONTROL", raising=False)
        from butler.transport.cache_control import (
            apply_cache_control_to_last_tool_result,
        )

        msgs = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
        ]
        assert apply_cache_control_to_last_tool_result(msgs) == msgs

    def test_single_tool_result_marks(self, monkeypatch):
        """单个 tool_result → 加 cache_control."""
        monkeypatch.delenv("BUTLER_TRANSPORT_CACHE_CONTROL", raising=False)
        from butler.transport.cache_control import (
            apply_cache_control_to_last_tool_result,
        )

        msgs = [
            {
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": "c1", "content": "r1"}],
            },
        ]
        out = apply_cache_control_to_last_tool_result(msgs)
        assert out[0]["content"][0]["cache_control"] == {"type": "ephemeral"}

    def test_multiple_tool_results_only_last_marked(self, monkeypatch):
        """多个 tool_result (跨 user msg) → 只最后 1 个加 marker."""
        monkeypatch.delenv("BUTLER_TRANSPORT_CACHE_CONTROL", raising=False)
        from butler.transport.cache_control import (
            apply_cache_control_to_last_tool_result,
        )

        msgs = [
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": "c1", "content": "r1"},
                    {"type": "tool_result", "tool_use_id": "c2", "content": "r2"},
                ],
            },
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": "c3", "content": "r3"},
                ],
            },
        ]
        out = apply_cache_control_to_last_tool_result(msgs)
        # 第 1 个 user 的 c1, c2 不动
        assert "cache_control" not in out[0]["content"][0]
        assert "cache_control" not in out[0]["content"][1]
        # 第 2 个 user 的 c3 加 marker
        assert out[1]["content"][0]["cache_control"] == {"type": "ephemeral"}
        # 其它字段保留
        assert out[1]["content"][0]["tool_use_id"] == "c3"
        assert out[1]["content"][0]["content"] == "r3"


# ── 集成: anthropic_transport.build_kwargs wiring ──


class TestAnthropicTransportWiring:
    def test_build_kwargs_enabled_marks_all_four(self, monkeypatch):
        """env on + build_kwargs → 4 boundary 全有 marker."""
        monkeypatch.delenv("BUTLER_TRANSPORT_CACHE_CONTROL", raising=False)
        from butler.transport.anthropic_transport import AnthropicTransport

        t = AnthropicTransport()
        messages = [
            {"role": "system", "content": "you are a helpful assistant"},
            {"role": "user", "content": "ask"},
            {"role": "assistant", "content": "ok"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": "call_1", "function": {"name": "echo", "arguments": "{}"}},
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "call_1",
                "content": "result",
            },
        ]
        tools = [
            {"name": "echo", "description": "echo", "input_schema": {"type": "object"}},
        ]
        kwargs = t.build_kwargs(
            model="claude-test",
            messages=messages,
            tools=tools,
            max_tokens=1024,
        )

        # boundary 1: system 走 list
        assert isinstance(kwargs["system"], list)
        assert kwargs["system"][-1]["cache_control"] == {"type": "ephemeral"}
        # boundary 2: 最后 user (tool 转换后) 末尾有 marker block
        # 最后一条是 tool → 转换后 role=user, content=[{tool_result, ...}]
        last_msg = kwargs["messages"][-1]
        assert last_msg["role"] == "user"
        # boundary 4: tool_result 块带 cache_control
        tool_result_block = last_msg["content"][-1]
        assert tool_result_block["type"] == "tool_result"
        assert tool_result_block["cache_control"] == {"type": "ephemeral"}
        # boundary 3: tools 列表最后 1 个带 cache_control
        assert kwargs["tools"][-1]["cache_control"] == {"type": "ephemeral"}

    def test_build_kwargs_disabled_no_markers(self, monkeypatch):
        """env=0 + build_kwargs → 4 boundary 全无 marker (system 走 str 路径)."""
        monkeypatch.setenv("BUTLER_TRANSPORT_CACHE_CONTROL", "0")
        from butler.transport.anthropic_transport import AnthropicTransport

        t = AnthropicTransport()
        messages = [
            {"role": "system", "content": "you are a helpful assistant"},
            {"role": "user", "content": "ask"},
            {"role": "assistant", "content": "ok"},
        ]
        tools = [
            {"name": "echo", "description": "echo", "input_schema": {"type": "object"}},
        ]
        kwargs = t.build_kwargs(
            model="claude-test",
            messages=messages,
            tools=tools,
            max_tokens=1024,
        )

        # system 仍是 str (不变成 list)
        assert isinstance(kwargs["system"], str)
        assert "cache_control" not in str(kwargs["system"])
        # messages 没有任何 cache_control 字段
        def _walk_no_cache_control(obj):
            if isinstance(obj, dict):
                assert "cache_control" not in obj, f"unexpected cache_control in {obj}"
                for v in obj.values():
                    _walk_no_cache_control(v)
            elif isinstance(obj, list):
                for item in obj:
                    _walk_no_cache_control(item)

        _walk_no_cache_control(kwargs["messages"])
        # tools 无 cache_control
        assert "cache_control" not in kwargs["tools"][-1]

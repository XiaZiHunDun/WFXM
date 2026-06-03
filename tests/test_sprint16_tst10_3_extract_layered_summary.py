"""Sprint 10 backlog TST-10-3: butler.session.post_session_layered.extract_layered_summary 0 直测.

bug: butler/session/post_session_layered.py:32-63 extract_layered_summary 是 session
end 的人格/偏好/经验三层摘要, audit 标记 0 直测。

修复: 补全分支覆盖, 不改实现 (实现正确, 只是没测)。
覆盖:
- 关闭路径: BUTLER_POST_SESSION_LAYERED=0/未设 → 返 empty, 不调 llm_call
- 缺 llm_call → 返 empty
- 短 transcript (<200 chars) → 返 empty (即使 enabled + 有 llm_call)
- happy path sync llm_call (返 JSON 字符串)
- happy path async llm_call (返 coroutine)
- 响应含 markdown code fence (json 中混入 ``` 也能解析)
- LLM 抛异常 → 返 empty (logger.debug)
- LLM 返非 JSON → 返 empty
- LLM 返非 dict (list/str) → 返 empty
- persona/preference/experience 各自 list 化, 截到 3 条
- 单条字符串 > 240 chars → 截到 240
- 单条空字符串 → 跳过
- 非 list 字段 (dict/str) → 返 []
- 缺字段 → 返 []
- 空 dict → 全空 list
- 静态契约: 导出符号 + 禁用默认 False
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from butler.session import post_session_layered
from butler.session.post_session_layered import (
    _LAYERED_PROMPT,
    extract_layered_summary,
    post_session_layered_enabled,
)


# ── 公共 fixture: 默认禁用, 减少环境干扰 ──


@pytest.fixture(autouse=True)
def _default_disabled(monkeypatch):
    """默认 BUTLER_POST_SESSION_LAYERED=0, 测试 enabled 行为时单独启用。"""
    monkeypatch.delenv("BUTLER_POST_SESSION_LAYERED", raising=False)


@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setenv("BUTLER_POST_SESSION_LAYERED", "1")
    return monkeypatch


def _gen_messages(n_turns: int = 10) -> list[dict]:
    """生成 n 轮 user/assistant 交替, 单条 50 字符, 总长 ~ n*100 chars。"""
    msgs = []
    for i in range(n_turns):
        msgs.append({"role": "user", "content": f"用户消息 {i}: " + "x" * 50})
        msgs.append({"role": "assistant", "content": f"助手回复 {i}: " + "y" * 50})
    return msgs


# ── 关闭路径 ──


class TestDisabled:
    def test_disabled_by_default(self):
        assert post_session_layered_enabled() is False

    @pytest.mark.asyncio
    async def test_disabled_returns_empty_without_calling_llm(self):
        llm = MagicMock()
        result = await extract_layered_summary(_gen_messages(), llm)
        assert result == {"persona": [], "preference": [], "experience": []}
        llm.assert_not_called()

    @pytest.mark.asyncio
    async def test_explicit_disabled_returns_empty(self, monkeypatch):
        monkeypatch.setenv("BUTLER_POST_SESSION_LAYERED", "0")
        llm = MagicMock()
        result = await extract_layered_summary(_gen_messages(), llm)
        assert result == {"persona": [], "preference": [], "experience": []}
        llm.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_llm_call_returns_empty(self, enabled):
        result = await extract_layered_summary(_gen_messages(), None)
        assert result == {"persona": [], "preference": [], "experience": []}


# ── 短 transcript 早退 ──


class TestShortTranscript:
    @pytest.mark.asyncio
    async def test_short_messages_returns_empty(self, enabled):
        """< 200 chars 短 transcript → 早退, 不调 llm_call。"""
        llm = MagicMock()
        msgs = [{"role": "user", "content": "hi"}]
        result = await extract_layered_summary(msgs, llm)
        assert result == {"persona": [], "preference": [], "experience": []}
        llm.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_messages_returns_empty(self, enabled):
        result = await extract_layered_summary([], MagicMock())
        assert result == {"persona": [], "preference": [], "experience": []}


# ── Happy path: sync llm_call ──


class TestSyncLlmCall:
    @pytest.mark.asyncio
    async def test_sync_llm_returns_three_lists(self, enabled):
        llm = MagicMock(return_value=json.dumps({
            "persona": ["用户是开发者"],
            "preference": ["喜欢简洁回答"],
            "experience": ["使用中文"],
        }))
        result = await extract_layered_summary(_gen_messages(20), llm)
        assert result["persona"] == ["用户是开发者"]
        assert result["preference"] == ["喜欢简洁回答"]
        assert result["experience"] == ["使用中文"]
        llm.assert_called_once()
        # prompt 包含 _LAYERED_PROMPT 的占位说明
        call_prompt = llm.call_args.args[0]
        assert "persona" in call_prompt
        assert "[USER]" in call_prompt or "[ASSISTANT]" in call_prompt

    @pytest.mark.asyncio
    async def test_response_with_markdown_fence_parsed(self, enabled):
        """LLM 返 ```json\\n{...}\\n``` → _parse_json_from_response 仍能抽 JSON。"""
        response = '```json\n{"persona": ["A"], "preference": [], "experience": []}\n```'
        llm = MagicMock(return_value=response)
        result = await extract_layered_summary(_gen_messages(20), llm)
        assert result["persona"] == ["A"]

    @pytest.mark.asyncio
    async def test_response_with_surrounding_text_parsed(self, enabled):
        """LLM 返 'Here is the JSON: {\\"persona\\": [\\"X\\"]} done' → 抽 {} 解析。"""
        response = 'Here is the JSON: {"persona": ["X"], "preference": [], "experience": []} done'
        llm = MagicMock(return_value=response)
        result = await extract_layered_summary(_gen_messages(20), llm)
        assert result["persona"] == ["X"]


# ── Happy path: async llm_call ──


class TestAsyncLlmCall:
    @pytest.mark.asyncio
    async def test_async_llm_awaited(self, enabled):
        """llm_call 返 coroutine → 自动 await。"""
        async def async_llm(prompt):
            return json.dumps({
                "persona": ["async-persona"],
                "preference": ["async-pref"],
                "experience": ["async-exp"],
            })

        result = await extract_layered_summary(_gen_messages(20), async_llm)
        assert result["persona"] == ["async-persona"]
        assert result["preference"] == ["async-pref"]
        assert result["experience"] == ["async-exp"]


# ── 异常 / 坏响应 → 返 empty, 不抛 ──


class TestErrorHandling:
    @pytest.mark.asyncio
    async def test_llm_call_exception_returns_empty(self, enabled, caplog):
        """llm_call 抛异常 → 返 empty, 不向上抛。"""
        def bad_llm(prompt):
            raise RuntimeError("LLM unavailable")

        with caplog.at_level("DEBUG", logger="butler.session.post_session_layered"):
            result = await extract_layered_summary(_gen_messages(20), bad_llm)
        assert result == {"persona": [], "preference": [], "experience": []}

    @pytest.mark.asyncio
    async def test_async_llm_exception_returns_empty(self, enabled):
        async def bad_llm(prompt):
            raise RuntimeError("kaboom")

        result = await extract_layered_summary(_gen_messages(20), bad_llm)
        assert result == {"persona": [], "preference": [], "experience": []}

    @pytest.mark.asyncio
    async def test_non_json_response_returns_empty(self, enabled):
        """LLM 返 'I cannot help' (无 {) → 解析返 None → 返 empty。"""
        llm = MagicMock(return_value="I cannot help with that.")
        result = await extract_layered_summary(_gen_messages(20), llm)
        assert result == {"persona": [], "preference": [], "experience": []}

    @pytest.mark.asyncio
    async def test_invalid_json_response_returns_empty(self, enabled):
        """LLM 返 {invalid json} → json.JSONDecodeError → 返 None → empty。"""
        llm = MagicMock(return_value="{not valid json}")
        result = await extract_layered_summary(_gen_messages(20), llm)
        assert result == {"persona": [], "preference": [], "experience": []}

    @pytest.mark.asyncio
    async def test_list_response_returns_empty(self, enabled):
        """LLM 返 [...] (顶层是 list 而非 dict) → 返 empty。"""
        llm = MagicMock(return_value="[1, 2, 3]")
        result = await extract_layered_summary(_gen_messages(20), llm)
        assert result == {"persona": [], "preference": [], "experience": []}

    @pytest.mark.asyncio
    async def test_empty_dict_response_returns_empty_lists(self, enabled):
        """LLM 返 {} → 三个字段都为空 list。"""
        llm = MagicMock(return_value="{}")
        result = await extract_layered_summary(_gen_messages(20), llm)
        assert result == {"persona": [], "preference": [], "experience": []}


# ── 列表截断与过滤 ──


class TestListTruncation:
    @pytest.mark.asyncio
    async def test_caps_each_field_to_3_items(self, enabled):
        """每个字段最多 3 条 (audit: 最多3条)。"""
        llm = MagicMock(return_value=json.dumps({
            "persona": ["p1", "p2", "p3", "p4", "p5"],
            "preference": ["x1", "x2", "x3", "x4"],
            "experience": ["e1", "e2", "e3", "e4", "e5", "e6"],
        }))
        result = await extract_layered_summary(_gen_messages(20), llm)
        assert len(result["persona"]) == 3
        assert len(result["preference"]) == 3
        assert len(result["experience"]) == 3

    @pytest.mark.asyncio
    async def test_caps_single_string_to_240_chars(self, enabled):
        """单条字符串 > 240 字符 → 截到 240。"""
        long = "a" * 500
        llm = MagicMock(return_value=json.dumps({
            "persona": [long],
            "preference": [],
            "experience": [],
        }))
        result = await extract_layered_summary(_gen_messages(20), llm)
        assert len(result["persona"][0]) == 240

    @pytest.mark.asyncio
    async def test_skips_empty_strings_after_strip(self, enabled):
        """空字符串 / 纯空白条目 → 跳过。"""
        llm = MagicMock(return_value=json.dumps({
            "persona": ["real", "   ", "", "\t\n"],
            "preference": [],
            "experience": [],
        }))
        result = await extract_layered_summary(_gen_messages(20), llm)
        assert result["persona"] == ["real"]

    @pytest.mark.asyncio
    async def test_non_list_field_returns_empty_list(self, enabled):
        """字段是 dict/str/int 而不是 list → 返 []。"""
        llm = MagicMock(return_value=json.dumps({
            "persona": {"name": "x"},  # dict 而非 list
            "preference": "string",   # str 而非 list
            "experience": 42,         # int
        }))
        result = await extract_layered_summary(_gen_messages(20), llm)
        assert result["persona"] == []
        assert result["preference"] == []
        assert result["experience"] == []

    @pytest.mark.asyncio
    async def test_missing_field_returns_empty_list(self, enabled):
        """LLM 响应缺某字段 → 缺字段返 []。"""
        llm = MagicMock(return_value=json.dumps({
            "persona": ["only-persona"],
        }))
        result = await extract_layered_summary(_gen_messages(20), llm)
        assert result["persona"] == ["only-persona"]
        assert result["preference"] == []
        assert result["experience"] == []

    @pytest.mark.asyncio
    async def test_none_field_returns_empty_list(self, enabled):
        """字段值是 None → 返 [] (data.get(key) or [])。"""
        llm = MagicMock(return_value=json.dumps({
            "persona": None,
            "preference": None,
            "experience": None,
        }))
        result = await extract_layered_summary(_gen_messages(20), llm)
        assert result == {"persona": [], "preference": [], "experience": []}

    @pytest.mark.asyncio
    async def test_string_items_coerced_to_str(self, enabled):
        """列表中非 str 元素 → str(x) 转换。"""
        llm = MagicMock(return_value=json.dumps({
            "persona": [123, 1.5, True],
            "preference": [],
            "experience": [],
        }))
        result = await extract_layered_summary(_gen_messages(20), llm)
        assert result["persona"] == ["123", "1.5", "True"]


# ── 静态契约 ──


class TestStaticContract:
    def test_post_session_layered_enabled_default_false(self, monkeypatch):
        monkeypatch.delenv("BUTLER_POST_SESSION_LAYERED", raising=False)
        assert post_session_layered_enabled() is False

    def test_post_session_layered_enabled_truthy(self, monkeypatch):
        monkeypatch.setenv("BUTLER_POST_SESSION_LAYERED", "1")
        assert post_session_layered_enabled() is True

    def test_exports_required_symbols(self):
        for name in ("extract_layered_summary", "post_session_layered_enabled"):
            assert hasattr(post_session_layered, name), (
                f"post_session_layered 应导出 {name}"
            )

    def test_layered_prompt_contains_three_categories(self):
        """_LAYERED_PROMPT 应包含 3 个分类 (persona/preference/experience)。"""
        assert "persona" in _LAYERED_PROMPT
        assert "preference" in _LAYERED_PROMPT
        assert "experience" in _LAYERED_PROMPT
        assert "{transcript}" in _LAYERED_PROMPT

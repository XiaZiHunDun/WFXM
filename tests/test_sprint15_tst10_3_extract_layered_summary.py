"""Sprint 15 TST-10-3: butler.session.post_session_layered.extract_layered_summary 直测.

extract_layered_summary 是 persona/preference/experience 三层摘要提取函数。
之前 0 个直测，仅通过 post_session 集成路径间接覆盖。

关键行为：
  - 默认 disabled (BUTLER_POST_SESSION_LAYERED) → 返回空
  - llm_call 为空 → 返回空
  - transcript < 200 chars → 返回空
  - llm_call 可同步/异步；解析失败/非 dict → 返回空
  - 每层最多 3 条；每条 strip + 截断 240 chars
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest


# ── 辅助: 构造长 transcript 的 messages ─────────────────────


def _long_messages(n_user: int = 3, n_assistant: int = 3) -> list[dict]:
    """构造足够长的对话以超过 200 chars 阈值。"""
    msgs: list[dict] = []
    for i in range(n_user):
        msgs.append({
            "role": "user",
            "content": f"用户第 {i+1} 段问询：" + ("这是一些占位文字 " * 20),
        })
    for i in range(n_assistant):
        msgs.append({
            "role": "assistant",
            "content": f"助手第 {i+1} 段回答：" + ("这是一些占位文字 " * 20),
        })
    return msgs


def _short_messages() -> list[dict]:
    """不足 200 chars 的对话。"""
    return [{"role": "user", "content": "短问题"}]


# ── 禁用 / 缺依赖 ─────────────────────────────────────────────


class TestGateConditions:
    @pytest.mark.asyncio
    async def test_disabled_by_default_returns_empty(self, monkeypatch):
        """BUTLER_POST_SESSION_LAYERED 未设 → 立即返回 empty。"""
        from butler.session.post_session_layered import extract_layered_summary

        monkeypatch.delenv("BUTLER_POST_SESSION_LAYERED", raising=False)

        called = []
        def llm_call(prompt: str) -> str:
            called.append(prompt)
            return json.dumps({"persona": ["X"], "preference": [], "experience": []})

        out = await extract_layered_summary(_long_messages(), llm_call)

        assert out == {"persona": [], "preference": [], "experience": []}
        assert called == [], "disabled 时不应调用 llm_call"

    @pytest.mark.asyncio
    async def test_enabled_but_zero_disables(self, monkeypatch):
        """env 设 '0' 视为关闭。"""
        from butler.session.post_session_layered import extract_layered_summary

        monkeypatch.setenv("BUTLER_POST_SESSION_LAYERED", "0")

        called = []
        def llm_call(prompt: str) -> str:
            called.append(prompt)
            return "{}"

        out = await extract_layered_summary(_long_messages(), llm_call)

        assert out["persona"] == []
        assert out["preference"] == []
        assert out["experience"] == []
        assert called == []

    @pytest.mark.asyncio
    async def test_no_llm_call_returns_empty(self, monkeypatch):
        """llm_call=None → 立即返回 empty。"""
        from butler.session.post_session_layered import extract_layered_summary

        monkeypatch.setenv("BUTLER_POST_SESSION_LAYERED", "1")

        out = await extract_layered_summary(_long_messages(), None)

        assert out == {"persona": [], "preference": [], "experience": []}

    @pytest.mark.asyncio
    async def test_short_transcript_returns_empty(self, monkeypatch):
        """transcript < 200 chars → 即使 enabled 也返回 empty（避免无意义调用）。"""
        from butler.session.post_session_layered import extract_layered_summary

        monkeypatch.setenv("BUTLER_POST_SESSION_LAYERED", "1")

        called = []
        def llm_call(prompt: str) -> str:
            called.append(prompt)
            return json.dumps({
                "persona": ["should not appear"],
                "preference": [],
                "experience": [],
            })

        out = await extract_layered_summary(_short_messages(), llm_call)

        assert out["persona"] == []
        assert out["preference"] == []
        assert out["experience"] == []
        assert called == [], "短 transcript 不应触发 LLM 调用"


# ── LLM 同步/异步调用 ─────────────────────────────────────────


class TestLlmCallShape:
    @pytest.mark.asyncio
    async def test_sync_llm_call(self, monkeypatch):
        """llm_call 返回 str → 正常解析。"""
        from butler.session.post_session_layered import extract_layered_summary

        monkeypatch.setenv("BUTLER_POST_SESSION_LAYERED", "1")

        def llm_call(prompt: str) -> str:
            return json.dumps({
                "persona": ["技术导向", "简洁沟通"],
                "preference": ["喜欢表格", "倾向命令式"],
                "experience": ["用 QwenPaw 时优先中文"],
            })

        out = await extract_layered_summary(_long_messages(), llm_call)

        assert out["persona"] == ["技术导向", "简洁沟通"]
        assert out["preference"] == ["喜欢表格", "倾向命令式"]
        assert out["experience"] == ["用 QwenPaw 时优先中文"]

    @pytest.mark.asyncio
    async def test_async_llm_call(self, monkeypatch):
        """llm_call 返回 coroutine → 自动 await。"""
        from butler.session.post_session_layered import extract_layered_summary

        monkeypatch.setenv("BUTLER_POST_SESSION_LAYERED", "1")

        async def llm_call(prompt: str) -> str:
            await asyncio.sleep(0)
            return json.dumps({
                "persona": ["async user"],
                "preference": [],
                "experience": [],
            })

        out = await extract_layered_summary(_long_messages(), llm_call)

        assert out["persona"] == ["async user"]
        assert out["preference"] == []
        assert out["experience"] == []

    @pytest.mark.asyncio
    async def test_llm_call_prompt_contains_transcript(self, monkeypatch):
        """prompt 应包含对话内容（truncated to 8000 chars）。"""
        from butler.session.post_session_layered import extract_layered_summary

        monkeypatch.setenv("BUTLER_POST_SESSION_LAYERED", "1")

        seen: list[str] = []
        def llm_call(prompt: str) -> str:
            seen.append(prompt)
            return json.dumps({"persona": [], "preference": [], "experience": []})

        await extract_layered_summary(_long_messages(), llm_call)

        assert len(seen) == 1
        prompt = seen[0]
        assert "USER" in prompt or "user" in prompt
        assert "占位文字" in prompt or "用户" in prompt


# ── JSON 解析容错 ─────────────────────────────────────────────


class TestParseRobustness:
    @pytest.mark.asyncio
    async def test_invalid_json_returns_empty(self, monkeypatch):
        """LLM 返回非 JSON → 返回 empty。"""
        from butler.session.post_session_layered import extract_layered_summary

        monkeypatch.setenv("BUTLER_POST_SESSION_LAYERED", "1")

        def llm_call(prompt: str) -> str:
            return "这不是 JSON 格式"

        out = await extract_layered_summary(_long_messages(), llm_call)

        assert out == {"persona": [], "preference": [], "experience": []}

    @pytest.mark.asyncio
    async def test_json_with_markdown_fences_parsed(self, monkeypatch):
        """LLM 返回带 markdown ```json ... ``` 包裹 → 仍可解析。"""
        from butler.session.post_session_layered import extract_layered_summary

        monkeypatch.setenv("BUTLER_POST_SESSION_LAYERED", "1")

        def llm_call(prompt: str) -> str:
            return '```json\n{"persona": ["p1"], "preference": [], "experience": []}\n```'

        out = await extract_layered_summary(_long_messages(), llm_call)

        assert out["persona"] == ["p1"]

    @pytest.mark.asyncio
    async def test_non_dict_json_returns_empty(self, monkeypatch):
        """LLM 返回合法 JSON 但不是 object → 返回 empty。"""
        from butler.session.post_session_layered import extract_layered_summary

        monkeypatch.setenv("BUTLER_POST_SESSION_LAYERED", "1")

        def llm_call(prompt: str) -> str:
            return json.dumps([1, 2, 3])  # list 而非 dict

        out = await extract_layered_summary(_long_messages(), llm_call)

        assert out == {"persona": [], "preference": [], "experience": []}

    @pytest.mark.asyncio
    async def test_llm_raises_returns_empty(self, monkeypatch):
        """llm_call 抛异常 → 静默返回 empty（不污染会话流程）。"""
        from butler.session.post_session_layered import extract_layered_summary

        monkeypatch.setenv("BUTLER_POST_SESSION_LAYERED", "1")

        def llm_call(prompt: str) -> str:
            raise RuntimeError("LLM service down")

        out = await extract_layered_summary(_long_messages(), llm_call)

        assert out == {"persona": [], "preference": [], "experience": []}

    @pytest.mark.asyncio
    async def test_llm_returns_none_returns_empty(self, monkeypatch):
        """llm_call 返回 None → 返回 empty。"""
        from butler.session.post_session_layered import extract_layered_summary

        monkeypatch.setenv("BUTLER_POST_SESSION_LAYERED", "1")

        def llm_call(prompt: str) -> None:
            return None

        out = await extract_layered_summary(_long_messages(), llm_call)

        assert out == {"persona": [], "preference": [], "experience": []}


# ── 列表归一化 ─────────────────────────────────────────────


class TestListNormalization:
    @pytest.mark.asyncio
    async def test_max_three_per_layer(self, monkeypatch):
        """每层最多保留 3 条。"""
        from butler.session.post_session_layered import extract_layered_summary

        monkeypatch.setenv("BUTLER_POST_SESSION_LAYERED", "1")

        def llm_call(prompt: str) -> str:
            return json.dumps({
                "persona": ["p1", "p2", "p3", "p4", "p5"],
                "preference": ["a", "b", "c", "d"],
                "experience": ["e1", "e2", "e3", "e4", "e5", "e6"],
            })

        out = await extract_layered_summary(_long_messages(), llm_call)

        assert len(out["persona"]) == 3
        assert len(out["preference"]) == 3
        assert len(out["experience"]) == 3
        assert out["persona"] == ["p1", "p2", "p3"]
        assert out["experience"] == ["e1", "e2", "e3"]

    @pytest.mark.asyncio
    async def test_long_string_truncated_to_240(self, monkeypatch):
        """单条超过 240 chars 截断。"""
        from butler.session.post_session_layered import extract_layered_summary

        monkeypatch.setenv("BUTLER_POST_SESSION_LAYERED", "1")

        long_str = "x" * 500

        def llm_call(prompt: str) -> str:
            return json.dumps({
                "persona": [long_str],
                "preference": [],
                "experience": [],
            })

        out = await extract_layered_summary(_long_messages(), llm_call)

        assert len(out["persona"]) == 1
        assert len(out["persona"][0]) == 240

    @pytest.mark.asyncio
    async def test_empty_strings_filtered(self, monkeypatch):
        """空白字符串被过滤掉。"""
        from butler.session.post_session_layered import extract_layered_summary

        monkeypatch.setenv("BUTLER_POST_SESSION_LAYERED", "1")

        def llm_call(prompt: str) -> str:
            return json.dumps({
                "persona": ["", "  ", "\t\n", "valid", "another"],
                "preference": ["", "p1"],
                "experience": ["e1", ""],
            })

        out = await extract_layered_summary(_long_messages(), llm_call)

        assert out["persona"] == ["valid", "another"]
        assert out["preference"] == ["p1"]
        assert out["experience"] == ["e1"]

    @pytest.mark.asyncio
    async def test_non_list_value_for_layer_becomes_empty(self, monkeypatch):
        """某层不是 list (e.g. string) → 视为空数组。"""
        from butler.session.post_session_layered import extract_layered_summary

        monkeypatch.setenv("BUTLER_POST_SESSION_LAYERED", "1")

        def llm_call(prompt: str) -> str:
            return json.dumps({
                "persona": "this is a string, not a list",
                "preference": 42,
                "experience": None,
            })

        out = await extract_layered_summary(_long_messages(), llm_call)

        assert out == {"persona": [], "preference": [], "experience": []}

    @pytest.mark.asyncio
    async def test_missing_keys_become_empty(self, monkeypatch):
        """响应缺某 key → 该层为空。"""
        from butler.session.post_session_layered import extract_layered_summary

        monkeypatch.setenv("BUTLER_POST_SESSION_LAYERED", "1")

        def llm_call(prompt: str) -> str:
            return json.dumps({"persona": ["only persona"]})

        out = await extract_layered_summary(_long_messages(), llm_call)

        assert out["persona"] == ["only persona"]
        assert out["preference"] == []
        assert out["experience"] == []

    @pytest.mark.asyncio
    async def test_non_string_items_coerced_to_string(self, monkeypatch):
        """列表中的非字符串元素被 str() 化（每层限 3 条）。"""
        from butler.session.post_session_layered import extract_layered_summary

        monkeypatch.setenv("BUTLER_POST_SESSION_LAYERED", "1")

        def llm_call(prompt: str) -> str:
            return json.dumps({
                "persona": [1, True, 3.14],
                "preference": [],
                "experience": [],
            })

        out = await extract_layered_summary(_long_messages(), llm_call)

        assert out["persona"] == ["1", "True", "3.14"]


# ── 完整性：返回 dict 必含三键 ───────────────────────────


class TestReturnContract:
    @pytest.mark.asyncio
    async def test_return_has_exactly_three_keys(self, monkeypatch):
        """返回 dict 必含 persona/preference/experience 三键。"""
        from butler.session.post_session_layered import extract_layered_summary

        monkeypatch.setenv("BUTLER_POST_SESSION_LAYERED", "1")

        def llm_call(prompt: str) -> str:
            return json.dumps({
                "persona": ["a"],
                "preference": ["b"],
                "experience": ["c"],
                "extra": "should be ignored",
            })

        out = await extract_layered_summary(_long_messages(), llm_call)

        assert set(out.keys()) == {"persona", "preference", "experience"}

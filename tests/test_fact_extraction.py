"""Tests for butler/core/fact_extraction.py — structured fact extraction.

Covers: extraction patterns (decisions, completions, preferences, file changes),
persistence (save/load), dedup, cap enforcement, anchor formatting, enabled flag.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.mark.unit
class TestFactExtractionEnabled:
    def test_enabled_by_default(self, monkeypatch):
        monkeypatch.delenv("BUTLER_FACT_EXTRACTION", raising=False)
        from butler.core.fact_extraction import fact_extraction_enabled
        assert fact_extraction_enabled() is True

    def test_disabled_via_env(self, monkeypatch):
        monkeypatch.setenv("BUTLER_FACT_EXTRACTION", "0")
        from butler.core.fact_extraction import fact_extraction_enabled
        assert fact_extraction_enabled() is False

    def test_enabled_with_true(self, monkeypatch):
        monkeypatch.setenv("BUTLER_FACT_EXTRACTION", "true")
        from butler.core.fact_extraction import fact_extraction_enabled
        assert fact_extraction_enabled() is True


@pytest.mark.unit
class TestExtractAssistantFacts:
    def test_decision_pattern_chinese(self):
        from butler.core.fact_extraction import _extract_facts_from_messages

        msgs = [{"role": "assistant", "content": "经过分析，决定：使用 FastAPI 作为后端框架，配合 SQLAlchemy ORM"}]
        facts = _extract_facts_from_messages(msgs)
        assert any(f["type"] == "decision" for f in facts)
        assert any("FastAPI" in f["value"] for f in facts)

    def test_completion_pattern(self):
        from butler.core.fact_extraction import _extract_facts_from_messages

        msgs = [{"role": "assistant", "content": "已完成 用户认证模块的重构"}]
        facts = _extract_facts_from_messages(msgs)
        assert any(f["type"] == "completion" for f in facts)

    def test_no_facts_from_empty_content(self):
        from butler.core.fact_extraction import _extract_facts_from_messages

        msgs = [{"role": "assistant", "content": ""}]
        facts = _extract_facts_from_messages(msgs)
        assert facts == []

    def test_multiple_facts_from_single_message(self):
        from butler.core.fact_extraction import _extract_facts_from_messages

        msgs = [{"role": "assistant", "content": (
            "结论：采用微服务架构，将系统分为三个独立服务。"
            "已完成 数据库迁移脚本的编写和测试。"
        )}]
        facts = _extract_facts_from_messages(msgs)
        types = {f["type"] for f in facts}
        assert "decision" in types
        assert "completion" in types


@pytest.mark.unit
class TestExtractUserFacts:
    def test_preference_negative(self):
        from butler.core.fact_extraction import _extract_facts_from_messages

        msgs = [{"role": "user", "content": "不要使用全局变量来管理状态"}]
        facts = _extract_facts_from_messages(msgs)
        assert any(f["type"] == "user_preference" for f in facts)

    def test_preference_positive(self):
        from butler.core.fact_extraction import _extract_facts_from_messages

        msgs = [{"role": "user", "content": "我希望在每个函数前加上类型注解"}]
        facts = _extract_facts_from_messages(msgs)
        assert any(f["type"] == "user_preference" for f in facts)

    def test_short_preference_ignored(self):
        from butler.core.fact_extraction import _extract_facts_from_messages

        msgs = [{"role": "user", "content": "不要abc"}]
        facts = _extract_facts_from_messages(msgs)
        prefs = [f for f in facts if f["type"] == "user_preference"]
        assert len(prefs) == 0


@pytest.mark.unit
class TestExtractToolFacts:
    def test_file_change_write(self):
        from butler.core.fact_extraction import _extract_facts_from_messages

        tool_result = json.dumps({"ok": True, "path": "src/main.py", "action": "write"})
        msgs = [
            {"role": "assistant", "content": "", "tool_calls": [{"id": "tc1", "function": {"name": "write_file"}}]},
            {"role": "tool", "tool_call_id": "tc1", "content": tool_result},
        ]
        facts = _extract_facts_from_messages(msgs)
        assert any(f["type"] == "file_change" for f in facts)
        assert any("src/main.py" in f["value"] for f in facts)

    def test_file_change_patch(self):
        from butler.core.fact_extraction import _extract_facts_from_messages

        tool_result = json.dumps({"ok": True, "path": "config.yaml", "action": "patch"})
        msgs = [
            {"role": "assistant", "content": "", "tool_calls": [{"id": "tc2", "function": {"name": "patch_file"}}]},
            {"role": "tool", "tool_call_id": "tc2", "content": tool_result},
        ]
        facts = _extract_facts_from_messages(msgs)
        changes = [f for f in facts if f["type"] == "file_change"]
        assert any("modified" in f["value"] for f in changes)

    def test_pim_tool_skipped(self):
        from butler.core.fact_extraction import _extract_facts_from_messages

        tool_result = json.dumps({"ok": True, "path": "~/.butler/expenses/e1.json"})
        msgs = [
            {"role": "assistant", "content": "", "tool_calls": [{"id": "tc3", "function": {"name": "expense_add"}}]},
            {"role": "tool", "tool_call_id": "tc3", "content": tool_result},
        ]
        facts = _extract_facts_from_messages(msgs)
        assert len(facts) == 0

    def test_non_json_tool_content_ignored(self):
        from butler.core.fact_extraction import _extract_facts_from_messages

        msgs = [
            {"role": "assistant", "content": "", "tool_calls": [{"id": "tc4", "function": {"name": "search"}}]},
            {"role": "tool", "tool_call_id": "tc4", "content": "plain text result"},
        ]
        facts = _extract_facts_from_messages(msgs)
        assert len(facts) == 0


@pytest.mark.unit
class TestFactPersistence:
    def test_save_and_load(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
        from butler.config import reload_butler_settings
        reload_butler_settings()

        from butler.core.fact_extraction import load_facts, save_facts

        sk = "test-session-1"
        facts = [
            {"type": "decision", "value": "使用 Redis 做缓存", "ts": 1.0},
            {"type": "completion", "value": "完成了 API 端点", "ts": 2.0},
        ]
        save_facts(sk, facts)
        loaded = load_facts(sk)
        assert len(loaded) == 2
        assert loaded[0]["value"] == "使用 Redis 做缓存"

    def test_load_nonexistent_returns_empty(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
        from butler.config import reload_butler_settings
        reload_butler_settings()

        from butler.core.fact_extraction import load_facts
        assert load_facts("nonexistent") == []

    def test_cap_enforcement(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
        from butler.config import reload_butler_settings
        reload_butler_settings()

        from butler.core.fact_extraction import _MAX_FACTS_PER_SESSION, load_facts, save_facts

        sk = "cap-test"
        big = [{"type": "decision", "value": f"fact-{i}", "ts": float(i)} for i in range(80)]
        save_facts(sk, big)
        loaded = load_facts(sk)
        assert len(loaded) == _MAX_FACTS_PER_SESSION
        assert loaded[-1]["value"] == "fact-79"

    def test_corrupt_json_returns_empty(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
        from butler.config import reload_butler_settings
        reload_butler_settings()

        from butler.core.fact_extraction import _facts_path, load_facts

        sk = "corrupt"
        path = _facts_path(sk)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("not valid json{{{", encoding="utf-8")
        assert load_facts(sk) == []


@pytest.mark.unit
class TestExtractPreCompactFacts:
    def test_extracts_and_persists(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
        monkeypatch.setenv("BUTLER_FACT_EXTRACTION", "1")
        from butler.config import reload_butler_settings
        reload_butler_settings()

        from butler.core.fact_extraction import extract_pre_compact_facts, load_facts

        sk = "compact-test"
        messages = [
            {"role": "assistant", "content": "决定：采用事件驱动架构来处理异步消息"}
        ]
        new_facts = extract_pre_compact_facts(sk, messages)
        assert len(new_facts) >= 1
        persisted = load_facts(sk)
        assert len(persisted) >= 1

    def test_dedup_same_value(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
        monkeypatch.setenv("BUTLER_FACT_EXTRACTION", "1")
        from butler.config import reload_butler_settings
        reload_butler_settings()

        from butler.core.fact_extraction import extract_pre_compact_facts, load_facts

        sk = "dedup-test"
        messages = [
            {"role": "assistant", "content": "决定：使用 PostgreSQL 数据库作为后端存储"}
        ]
        extract_pre_compact_facts(sk, messages)
        extract_pre_compact_facts(sk, messages)
        persisted = load_facts(sk)
        pg_facts = [f for f in persisted if "PostgreSQL" in f.get("value", "")]
        assert len(pg_facts) == 1

    def test_disabled_returns_empty(self, monkeypatch):
        monkeypatch.setenv("BUTLER_FACT_EXTRACTION", "0")
        from butler.core.fact_extraction import extract_pre_compact_facts
        result = extract_pre_compact_facts("disabled-test", [{"role": "assistant", "content": "决定：不会被提取出来的事实数据"}])
        assert result == []


@pytest.mark.unit
class TestFormatFactsForAnchor:
    def test_empty_returns_empty_string(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
        from butler.config import reload_butler_settings
        reload_butler_settings()

        from butler.core.fact_extraction import format_facts_for_anchor
        assert format_facts_for_anchor("no-facts") == ""

    def test_formats_with_sections(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
        from butler.config import reload_butler_settings
        reload_butler_settings()

        from butler.core.fact_extraction import format_facts_for_anchor, save_facts

        sk = "anchor-test"
        save_facts(sk, [
            {"type": "decision", "value": "用 Redis 做缓存", "ts": 1.0},
            {"type": "completion", "value": "完成认证模块", "ts": 2.0},
            {"type": "user_preference", "value": "不用全局变量", "ts": 3.0},
        ])
        anchor = format_facts_for_anchor(sk)
        assert "会话关键事实" in anchor
        assert "决策" in anchor
        assert "Redis" in anchor
        assert "已完成" in anchor
        assert "用户偏好" in anchor

    def test_max_chars_truncation(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
        from butler.config import reload_butler_settings
        reload_butler_settings()

        from butler.core.fact_extraction import format_facts_for_anchor, save_facts

        sk = "truncate-test"
        save_facts(sk, [{"type": "decision", "value": "x" * 200, "ts": float(i)} for i in range(30)])
        anchor = format_facts_for_anchor(sk, max_chars=100)
        assert len(anchor) <= 100

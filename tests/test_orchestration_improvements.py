"""Tests for orchestration quality improvements:
#1 cron reminders, #2 vector store, #3 semantic routing,
#4 MCP self-service, #5 fact extraction, #6 skill preferred_tools.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _safe_env(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    monkeypatch.setenv("BUTLER_TOOL_SAFE_ROOT", str(tmp_path))


# ── #1 Cron Reminders ──


class TestCronReminders:
    def test_parse_cron_alias(self):
        from butler.tools.reminder import _parse_cron_schedule

        assert _parse_cron_schedule("每天") == "0 9 * * *"
        assert _parse_cron_schedule("工作日") == "0 9 * * 1-5"
        assert _parse_cron_schedule("每小时") == "0 * * * *"
        assert _parse_cron_schedule("每周一") == "0 9 * * 1"

    def test_parse_natural_cron(self):
        from butler.tools.reminder import _parse_cron_schedule

        assert _parse_cron_schedule("每天 8:30") == "30 8 * * *"
        assert _parse_cron_schedule("每天 22:00") == "0 22 * * *"

    def test_parse_raw_cron(self):
        from butler.tools.reminder import _parse_cron_schedule

        assert _parse_cron_schedule("0 9 * * 1-5") == "0 9 * * 1-5"
        assert _parse_cron_schedule("*/15 * * * *") == "*/15 * * * *"

    def test_parse_non_cron_returns_none(self):
        from butler.tools.reminder import _parse_cron_schedule

        assert _parse_cron_schedule("30分钟") is None
        assert _parse_cron_schedule("14:00") is None
        assert _parse_cron_schedule("abc xyz") is None

    def test_set_recurring_reminder(self):
        from butler.tools.reminder import tool_set_reminder

        result = json.loads(tool_set_reminder("每日站会", "每天 9:00"))
        assert result["ok"] is True
        assert result["recurring"] is True
        assert result["cron"] == "0 9 * * *"
        assert "next_fire" in result

    def test_poll_reschedules_recurring(self, tmp_path, monkeypatch):
        from butler.tools.reminder import _save_reminder, poll_due_reminders

        reminder = {
            "id": "test_recur",
            "message": "test",
            "cron": "0 * * * *",
            "due_ts": time.time() - 10,
            "due_human": "2026-01-01 00:00",
            "created_ts": time.time() - 100,
            "status": "pending",
            "recurring": True,
            "fire_count": 0,
        }
        _save_reminder(reminder)

        fired = poll_due_reminders()
        assert len(fired) == 1
        assert fired[0]["message"] == "test"

        from butler.tools.reminder import _load_all

        reloaded = _load_all()
        recur = [r for r in reloaded if r["id"] == "test_recur"]
        assert len(recur) == 1
        assert recur[0]["status"] == "pending"
        assert recur[0]["due_ts"] > time.time()
        assert recur[0]["fire_count"] == 1


# ── #2 Vector Store ──


class TestVectorStore:
    def test_in_memory_store_add_query(self, tmp_path, monkeypatch):
        from butler.memory.vector_store import InMemoryVectorStore

        store = InMemoryVectorStore()
        store.add("d1", "Python web framework", {"type": "note"})
        store.add("d2", "Machine learning with PyTorch", {"type": "note"})
        store.add("d3", "Grocery shopping list", {"type": "life"})

        assert store.count() == 3

        results = store.query("programming language", top_k=2)
        assert len(results) <= 2
        assert all("id" in r for r in results)
        assert all("score" in r for r in results)

    def test_in_memory_store_where_filter(self, tmp_path, monkeypatch):
        from butler.memory.vector_store import InMemoryVectorStore

        store = InMemoryVectorStore()
        store.add("d1", "Python code", {"type": "dev"})
        store.add("d2", "Buy milk", {"type": "life"})

        results = store.query("code", where={"type": "dev"})
        assert all(r["metadata"]["type"] == "dev" for r in results)

    def test_in_memory_store_delete(self, tmp_path, monkeypatch):
        from butler.memory.vector_store import InMemoryVectorStore

        store = InMemoryVectorStore()
        store._docs.clear()
        store.add("d1", "test", {})
        assert store.count() == 1
        assert store.delete("d1") is True
        assert store.count() == 0

    def test_get_vector_store_fallback(self, tmp_path, monkeypatch):
        from butler.memory.vector_store import _STORE_CACHE, get_vector_store

        _STORE_CACHE.clear()
        store = get_vector_store("test_isolated")
        store_count_before = store.count()
        store.add("test_fb", "test", {})
        assert store.count() == store_count_before + 1
        _STORE_CACHE.clear()


# ── #3 Semantic Routing ──


class TestSemanticRouting:
    def test_skill_router_preserves_triggers(self):
        from butler.skills.router import SkillRouter

        skills = [
            {"name": "deploy", "description": "部署流水线", "triggers": ["部署", "deploy"]},
            {"name": "test", "description": "测试策略", "triggers": ["测试", "test"]},
        ]
        router = SkillRouter(skills)
        matched = router.match("帮我部署一下", top_k=3)
        assert any(s["name"] == "deploy" for s in matched)
        assert matched[0]["match_score"] >= 0.9

    def test_skill_router_get_preferred_tools(self):
        from butler.skills.router import SkillRouter

        skills = [
            {
                "name": "code-review",
                "description": "代码审查",
                "triggers": ["代码审查", "review"],
                "preferred_tools": ["read_file", "search_files", "git_diff"],
            },
        ]
        router = SkillRouter(skills)
        pt = router.get_preferred_tools("帮我做代码审查")
        assert "read_file" in pt
        assert "git_diff" in pt

    def test_skill_router_payload_includes_preferred_tools(self):
        from butler.skills.router import SkillRouter

        skills = [
            {
                "name": "deploy",
                "description": "部署",
                "triggers": ["部署"],
                "preferred_tools": ["terminal"],
            },
        ]
        router = SkillRouter(skills)
        matched = router.match("部署")
        assert matched[0]["preferred_tools"] == ["terminal"]


# ── #4 MCP Self-Service ──


class TestMcpSelfService:
    def test_catalog_search(self, monkeypatch):
        mock_entry = MagicMock()  # noqa: magicmock-no-spec — complex facade, spec= 收益低
        mock_entry.id = "github"
        mock_entry.title = "GitHub"
        mock_entry.description = "GitHub integration"
        mock_entry.transport = "stdio"
        mock_entry.trust = "trusted"

        mock_svc = MagicMock()  # noqa: magicmock-no-spec — complex facade, spec= 收益低
        mock_svc.search.return_value = [mock_entry]
        mock_svc.list_installed_ids.return_value = []

        with patch("butler.registry.mcp_catalog.McpCatalogService", return_value=mock_svc):
            from butler.tools.mcp_self_service import _tool_mcp_catalog_search

            result = json.loads(_tool_mcp_catalog_search(query="github"))
            assert result["ok"] is True
            assert result["count"] == 1
            assert result["results"][0]["id"] == "github"

    def test_list_installed(self, monkeypatch):
        mock_svc = MagicMock()  # noqa: magicmock-no-spec — complex facade, spec= 收益低
        mock_svc.list_installed_ids.return_value = ["github", "slack"]
        mock_svc.load_lock_summary.return_value = {"servers": {}}

        with patch("butler.registry.mcp_catalog.McpCatalogService", return_value=mock_svc):
            from butler.tools.mcp_self_service import _tool_mcp_list_installed

            result = json.loads(_tool_mcp_list_installed())
            assert result["ok"] is True
            assert result["count"] == 2

    def test_install_missing_id(self):
        from butler.tools.mcp_self_service import _tool_mcp_install

        result = json.loads(_tool_mcp_install(""))
        assert result["ok"] is False
        assert "required" in result["error"]

    def test_install_runs_extension_verify_hint(self, monkeypatch):
        from butler.tools.mcp_self_service import _tool_mcp_install

        monkeypatch.setenv("BUTLER_MCP_ENABLED", "1")
        with patch("butler.registry.mcp_install.install_catalog_server", return_value=(True, "installed")):
            with patch("butler.mcp.extension_manifest.get_manifest_by_server_id") as mock_manifest:
                mock_manifest.return_value = type(
                    "M",
                    (),
                    {
                        "id": "github-readonly",
                        "ext_id": "ext-4",
                        "verify_phrases": ("列出我的 GitHub 仓库",),
                        "secrets": (),
                    },
                )()
                with patch("butler.mcp.extension_verify.verify_for_server_id") as mock_verify:
                    from butler.mcp.extension_verify import VerifyReport

                    mock_verify.return_value = VerifyReport(
                        ext_id="github-readonly",
                        ok=True,
                        at="2026-06-22T00:00:00+00:00",
                    )
                    with patch("butler.mcp.extension_verify.write_verify_cache"):
                        result = json.loads(_tool_mcp_install("github"))
        assert result["ok"] is True
        assert "extension_verify" in result
        assert result["extension_verify"]["acceptance_phrases"]


# ── #5 Fact Extraction ──


class TestFactExtraction:
    def test_extract_decision(self, tmp_path, monkeypatch):
        from butler.core.fact_extraction import _extract_facts_from_messages

        messages = [
            {"role": "assistant", "content": "经过分析，决定：采用 ChromaDB 作为向量存储后端，因为它支持嵌入式部署。"},
        ]
        facts = _extract_facts_from_messages(messages)
        assert any(f["type"] == "decision" for f in facts)

    def test_extract_completion(self, tmp_path, monkeypatch):
        from butler.core.fact_extraction import _extract_facts_from_messages

        messages = [
            {"role": "assistant", "content": "已完成 reminder 模块的 cron 支持改造。"},
        ]
        facts = _extract_facts_from_messages(messages)
        assert any(f["type"] == "completion" for f in facts)

    def test_extract_user_preference(self, tmp_path, monkeypatch):
        from butler.core.fact_extraction import _extract_facts_from_messages

        messages = [
            {"role": "user", "content": "不要引入 Redis，我想保持零外部依赖"},
        ]
        facts = _extract_facts_from_messages(messages)
        assert any(f["type"] == "user_preference" for f in facts)

    def test_save_and_load(self, tmp_path, monkeypatch):
        from butler.core.fact_extraction import load_facts, save_facts

        facts = [
            {"type": "decision", "value": "用 ChromaDB", "ts": time.time()},
            {"type": "completion", "value": "完成了 cron 提醒", "ts": time.time()},
        ]
        save_facts("test:session1", facts)
        loaded = load_facts("test:session1")
        assert len(loaded) == 2
        assert loaded[0]["value"] == "用 ChromaDB"

    def test_format_for_anchor(self, tmp_path, monkeypatch):
        from butler.core.fact_extraction import format_facts_for_anchor, save_facts

        facts = [
            {"type": "decision", "value": "用 ChromaDB", "ts": time.time()},
            {"type": "user_preference", "value": "不要 Redis", "ts": time.time()},
        ]
        save_facts("test:anchor", facts)
        anchor = format_facts_for_anchor("test:anchor")
        assert "会话关键事实" in anchor
        assert "ChromaDB" in anchor
        assert "Redis" in anchor

    def test_dedup_facts(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BUTLER_FACT_EXTRACTION", "1")
        from butler.core.fact_extraction import extract_pre_compact_facts, load_facts

        messages = [
            {"role": "assistant", "content": "决定：采用方案A作为最终实现"},
        ]
        extract_pre_compact_facts("s1", messages)
        extract_pre_compact_facts("s1", messages)

        facts = load_facts("s1")
        decision_facts = [f for f in facts if f["type"] == "decision"]
        values = [f["value"] for f in decision_facts]
        assert len(set(values)) == len(values)


# ── #6 Skill preferred_tools ──


class TestSkillPreferredToolsLink:
    def test_tool_selector_with_preferred(self):
        from butler.core.tool_selector import select_tools_for_context

        tools = [
            {"function": {"name": f"tool_{i}", "description": f"desc {i}"}}
            for i in range(20)
        ]
        tools.append({"function": {"name": "query_data", "description": "SQL data query"}})

        selected, diag = select_tools_for_context(
            tools,
            user_hint="帮我查一下数据",
            threshold=10,
            skill_preferred_tools={"query_data"},
        )
        names = {
            (d.get("function") or {}).get("name")
            for d in selected
        }
        assert "query_data" in names

    def test_tool_selector_without_preferred(self):
        from butler.core.tool_selector import select_tools_for_context

        tools = [
            {"function": {"name": f"tool_{i}", "description": f"desc {i}"}}
            for i in range(20)
        ]

        selected_without, _ = select_tools_for_context(
            tools, user_hint="random query", threshold=10,
        )
        selected_with, _ = select_tools_for_context(
            tools, user_hint="random query", threshold=10,
            skill_preferred_tools={"tool_15", "tool_18"},
        )
        names_with = {(d.get("function") or {}).get("name") for d in selected_with}
        assert "tool_15" in names_with
        assert "tool_18" in names_with

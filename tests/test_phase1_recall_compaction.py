"""Phase 1: recall-intent prefetch gate, P_r wiring, /压缩报告."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def _reset_metrics():
    from butler.memory.memory_metrics import MemoryMetricsCollector

    MemoryMetricsCollector.reset()
    yield
    MemoryMetricsCollector.reset()


def test_prefetch_skips_on_session_read_recall_intent(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))

    class _Exp:
        def search(self, *args, **kwargs):
            return [{"content": "docs/old-path.md", "project": "global"}]

    class _BM:
        experience = _Exp()

        def get_system_context(self, _proj):
            return "system ctx"

    orch = MagicMock()
    orch.butler_memory = _BM()
    orch.project_manager.get_current.return_value = None

    from butler.session.memory_prefetch import prefetch_turn_memory

    diag: dict = {}
    out = prefetch_turn_memory(
        orch,
        "把我们刚才读过哪些文件列个清单",
        diagnostics=diag,
    )
    assert out == ""
    assert diag.get("memory_prefetch_skipped") == "session_read_recall"
    assert diag.get("memory_experience_hits") is None


def test_skill_injection_skips_on_session_read_recall_intent():
    from butler.skills.injection_policy import resolve_skill_injection

    orch = MagicMock()
    orch.butler_memory = MagicMock()
    orch.butler_memory.experience.search.return_value = [
        {"content": "skill:deep-research", "tags": "skill:deep-research"},
    ]
    diag: dict = {}
    decision = resolve_skill_injection(
        orch,
        "列个清单",
        diagnostics=diag,
    )
    assert decision.skip is True
    assert decision.reason == "session_read_recall"


def test_finalize_prefetch_retrieval_metrics_updates_pr():
    from butler.memory.memory_metrics import get_collector
    from butler.memory.prefetch_retrieval_metrics import finalize_prefetch_retrieval_metrics

    get_collector().start_session("s1")
    get_collector().on_retrieval(total_returned=2, relevant=2, used_by_llm=0)
    health = {
        "memory_prefetch_retrieval_total": 2,
        "memory_prefetch_snippets": [
            "灵文试点统一测试日是 2026-05-22",
            "workflow_state.json 必须先读",
        ],
    }
    used = finalize_prefetch_retrieval_metrics(
        "s1",
        "主公，灵文试点统一测试日是 2026-05-22，已核对。",
        health,
    )
    assert used == 1
    mm = get_collector().get_session_metrics("s1")
    assert mm["retrieval_used_by_llm"] == 1
    assert health["memory_prefetch_retrieval_used"] == 1


def test_format_compaction_report_with_checkpoint(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    from butler.core.compaction_checkpoint import capture_checkpoint
    from butler.core.compaction_status import format_compaction_report

    sk = "wechat:u:proj"
    capture_checkpoint(
        sk,
        compression_summary="这是压缩摘要节选" * 3,
    )
    text = format_compaction_report(
        sk,
        {
            "hygiene_compressed": True,
            "hygiene_estimated_tokens": 40000,
            "hygiene_estimated_tokens_after": 12000,
        },
    )
    assert "压缩报告" in text
    assert "已压缩" in text
    assert "摘要节选" in text


def test_recall_intent_blocks_butler_recall_tool():
    from butler.core.session_recall_intent import check_session_read_recall_tool_block
    from butler.execution_context import use_session_read_recall_gate

    assert check_session_read_recall_tool_block("butler_recall") is None
    with use_session_read_recall_gate(True):
        block = check_session_read_recall_tool_block("butler_recall")
        assert block is not None
        assert "butler_recall" in block or "清单" in block
        assert check_session_read_recall_tool_block("read_file") is None


def test_local_project_inventory_intent_detected():
    from butler.core.session_recall_intent import (
        detect_local_project_inventory_banner,
        is_local_project_inventory_intent,
    )

    assert is_local_project_inventory_intent("分析一下灵文1号的代码架构是否需要改进")
    assert is_local_project_inventory_intent("看下项目目前都有哪些任务或者改进项待做")
    assert not is_local_project_inventory_intent("读一下 workflow_state")
    banner = detect_local_project_inventory_banner("列出改进项")
    assert banner is not None
    assert "local_project_inventory" in banner
    assert "interview-demo-backlog" in banner


def test_inventory_banner_embeds_backlog_when_workspace_present(tmp_path):
    from butler.core.session_recall_intent import detect_local_project_inventory_banner

    backlog = (
        "# 灵文1号 · 改进项\n\n"
        "## P0 — 演示前优先\n\n"
        "| # | 改进项 | 说明 |\n"
        "|---|--------|------|\n"
        "| 1 | Agent JSON schema 校验 | novel-factory 各 Agent 输出缺统一校验 |\n"
        "| 2 | workflow_state 微信口径 | /工作流 与 factory-status-daily 字段不一致 |\n"
        "| 3 | 测试残留目录清理 | MagicMock/、LingWen1/LingWen1/ 演示前宜删 |\n"
    )
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "interview-demo-backlog.md").write_text(backlog, encoding="utf-8")

    banner = detect_local_project_inventory_banner(
        "看下项目目前都有哪些任务或者改进项待做",
        workspace=tmp_path,
    )
    assert banner is not None
    assert "Agent JSON schema 校验" in banner
    assert "workflow_state 微信口径" in banner
    assert "MagicMock/" in banner
    assert "严格格式" in banner
    assert "禁止 read_file" in banner
    assert "禁止加粗" in banner


def test_inventory_banner_without_workspace_emits_fallback():
    from butler.core.session_recall_intent import detect_local_project_inventory_banner

    banner = detect_local_project_inventory_banner(
        "分析一下灵文1号的代码架构是否需要改进",
    )
    assert banner is not None
    assert "未读到 backlog" in banner
    assert "read_file docs/interview-demo-backlog.md" in banner


def test_inventory_intent_blocks_delegate_task():
    from butler.core.session_recall_intent import check_local_project_inventory_tool_block
    from butler.execution_context import use_local_project_inventory_gate

    assert check_local_project_inventory_tool_block("delegate_task") is None
    with use_local_project_inventory_gate(True):
        block = check_local_project_inventory_tool_block("delegate_task")
        assert block is not None
        assert "delegate_task" in block
        assert check_local_project_inventory_tool_block("read_file") is None


def test_skill_injection_skips_on_local_project_inventory_intent():
    from butler.skills.injection_policy import resolve_skill_injection

    orch = MagicMock()
    orch.butler_memory = MagicMock()
    orch.butler_memory.experience.search.return_value = [
        {"content": "skill:deep-research", "tags": "skill:deep-research"},
    ]
    decision = resolve_skill_injection(
        orch,
        "分析一下代码架构是否需要改进",
    )
    assert decision.skip is True
    assert decision.reason == "local_project_inventory"


def test_format_compaction_report_empty_epoch(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    from butler.core.compaction_status import format_compaction_report

    text = format_compaction_report("empty:session", {})
    assert "尚无压缩记录" in text


def test_format_compaction_report_includes_acl_fields():
    from butler.core.compaction_status import format_compaction_report

    text = format_compaction_report(
        "wechat:acl",
        {
            "hygiene_compressed": True,
            "compaction_view_version": "v1",
            "compaction_acl_shape": "v2_summary_tags",
            "compaction_hook_context": "hook摘要",
        },
    )
    assert "ACL 契约: v1" in text
    assert "ACL 形态: v2_summary_tags" in text
    assert "Hook 上下文" in text

"""Tests for degradation_registry (P0-B)."""

from __future__ import annotations

from butler.ops.degradation_registry import (
    clear_degradation,
    format_brief_line,
    format_diagnostic_lines,
    list_degradations,
    register_degradation,
    sync_memory_degradations_from_stats,
)


def setup_function() -> None:
    for rec in list_degradations():
        clear_degradation(rec.component)


def test_register_and_list():
    register_degradation("embedding", "请求 openai/x → hashing-v1")
    rows = list_degradations()
    assert len(rows) == 1
    assert rows[0].component == "embedding"


def test_format_brief_line_chinese_labels():
    register_degradation("embedding", "降级")
    register_degradation("recall", "仅 FTS")
    line = format_brief_line()
    assert line is not None
    assert "嵌入" in line
    assert "检索" in line


def test_format_brief_line_skills_label():
    register_degradation("skills", "merge fallback")
    line = format_brief_line()
    assert line is not None
    assert "Skill" in line


def test_sync_memory_degradations_from_stats():
    sync_memory_degradations_from_stats({
        "memory_offline": True,
        "memory_init_error": "boom",
        "embedding_degraded": True,
        "embedding_requested_provider": "openai",
        "embedding_requested_model": "text-embedding-3-small",
        "embedding_used_model": "hashing-v1",
        "rag_last_recall_degraded": True,
    })
    lines = format_diagnostic_lines()
    assert any("memory" in ln or "记忆" in ln for ln in lines)
    assert any("embedding" in ln for ln in lines)
    assert any("recall" in ln for ln in lines)


def test_clear_degradation():
    register_degradation("memory", "offline")
    clear_degradation("memory")
    assert format_brief_line() is None


def test_sync_mcp_degradations_when_disabled(monkeypatch):
    monkeypatch.setenv("BUTLER_MCP_ENABLED", "0")
    from butler.ops.degradation_registry import sync_mcp_degradations_at_startup

    sync_mcp_degradations_at_startup()
    rows = {r.component: r.reason for r in list_degradations()}
    assert "mcp" not in rows or "未开" in rows.get("mcp", "")

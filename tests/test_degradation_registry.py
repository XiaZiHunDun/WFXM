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


def test_refresh_degradations_for_owner_brief_merges_mcp(monkeypatch):
    from butler.ops.degradation_registry import (
        clear_degradation,
        list_degradations,
        refresh_degradations_for_owner_brief,
    )

    for rec in list_degradations():
        clear_degradation(rec.component)

    class _St:
        connected = False
        name = "test-server"

    monkeypatch.setattr(
        "butler.mcp.config.mcp_enabled",
        lambda: True,
    )
    monkeypatch.setattr(
        "butler.mcp.manager.get_manager",
        lambda: type("M", (), {"status_snapshot": lambda _self, _sk: [_St()]})(),
    )
    monkeypatch.setattr(
        "butler.ops.health_report.collect_mem_stats_for_health",
        lambda *_a, **_k: {},
    )

    line = refresh_degradations_for_owner_brief(object(), session_key="sk1")
    assert line is not None
    assert "MCP" in line or "mcp" in line.lower()
    rows = {r.component for r in list_degradations()}
    assert "mcp" in rows


def test_sync_mcp_degradations_when_disabled(monkeypatch):
    monkeypatch.setenv("BUTLER_MCP_ENABLED", "0")
    from butler.ops.degradation_registry import sync_mcp_degradations_at_startup

    sync_mcp_degradations_at_startup()
    rows = {r.component: r.reason for r in list_degradations()}
    assert "mcp" not in rows or "未开" in rows.get("mcp", "")


def test_sync_compaction_acl_from_metrics():
    from butler.ops.runtime_metrics import inc

    inc("compaction_acl_degraded", labels={"source": "test"})
    from butler.ops.degradation_registry import sync_compaction_acl_from_metrics

    sync_compaction_acl_from_metrics()
    rows = {r.component: r.reason for r in list_degradations()}
    assert "compaction_acl" in rows
    assert "降级" in rows["compaction_acl"]


def test_sync_compaction_acl_from_recent_skips():
    from butler.core.best_effort import record_best_effort_skip
    from butler.ops.degradation_registry import sync_compaction_acl_from_metrics

    record_best_effort_skip("compaction_acl.compress_messages", ValueError("x"))
    sync_compaction_acl_from_metrics()
    rows = {r.component: r.reason for r in list_degradations()}
    assert "compaction_acl" in rows


def test_metrics_sink_inc_forwards_labels():
    from butler.core.metrics_sink import inc, set_default_sink
    from butler.ops.runtime_metrics import counter_value
    from butler.ops.runtime_metrics_sink import RuntimeMetricsSink

    set_default_sink(RuntimeMetricsSink())
    inc("compaction_acl_degraded", labels={"source": "unit"})
    assert counter_value("compaction_acl_degraded", labels={"source": "unit"}) >= 1

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
        "butler.ops.degradation_registry_ops.mcp_enabled",
        lambda: True,
    )
    monkeypatch.setattr(
        "butler.ops.degradation_registry_ops.get_manager",
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


def test_format_diagnostic_lines_includes_since_ts():
    register_degradation("memory", "offline", detail="boom")
    lines = format_diagnostic_lines()
    joined = "\n".join(lines)
    assert "持续" in joined
    assert "memory" in joined


def test_register_degradation_sets_component_gauge():
    from butler.ops.runtime_metrics import snapshot_global

    register_degradation("embedding", "hashing fallback")
    snap = snapshot_global()
    gauges = snap.get("gauges") or {}
    assert gauges.get("degradation_active") == 1.0
    assert gauges.get("degradation_active{component=embedding}") == 1.0
    clear_degradation("embedding")
    snap2 = snapshot_global()
    gauges2 = snap2.get("gauges") or {}
    assert gauges2.get("degradation_active{component=embedding}") == 0.0


def test_register_degradation_logs_warning(caplog):
    import logging

    caplog.set_level(logging.WARNING)
    register_degradation("recall", "仅 FTS")
    assert any("Degradation active" in rec.message for rec in caplog.records)


def test_metrics_sink_inc_forwards_labels():
    from butler.core.metrics_sink import inc, set_default_sink
    from butler.ops.runtime_metrics import counter_value
    from butler.ops.runtime_metrics_sink import RuntimeMetricsSink

    set_default_sink(RuntimeMetricsSink())
    inc("compaction_acl_degraded", labels={"source": "unit"})
    assert counter_value("compaction_acl_degraded", labels={"source": "unit"}) >= 1


def test_skill_router_fallback_registers_and_clear():
    from butler.skills.injection_policy import (
        SkillInjectionDecision,
        record_skill_injection_metrics_safe,
    )

    record_skill_injection_metrics_safe(
        SkillInjectionDecision(
            mode="fallback",
            skip=False,
            skill_names=(),
            experience_hits=0,
            reason="router_fallback_no_experience",
        )
    )
    rows = {r.component: r.reason for r in list_degradations()}
    assert "skills" in rows
    assert "router_fallback_no_experience" in rows["skills"]

    record_skill_injection_metrics_safe(
        SkillInjectionDecision(
            mode="fallback",
            skip=False,
            skill_names=("ref-skill",),
            experience_hits=3,
            reason="experience_hit_with_ref",
        )
    )
    rows2 = {r.component for r in list_degradations()}
    assert "skills" not in rows2


def test_mcp_connect_failure_registers():
    from types import SimpleNamespace

    from butler.mcp.manager_ops import connect_handle_loud

    class _Status:
        last_error = ""
        degraded = False

    handle = SimpleNamespace(status=_Status())
    ok = connect_handle_loud(
        handle,
        server_id="test-srv-xyz",
        run_connect=lambda: (_ for _ in ()).throw(RuntimeError("connect refused")),
    )
    assert ok is False
    assert handle.status.degraded is True
    rows = {r.component: r.reason for r in list_degradations()}
    assert "mcp" in rows
    assert "test-srv-xyz" in rows["mcp"]


def test_compaction_tiktoken_fallback_registers(monkeypatch):
    import sys

    from butler.core.context_compressor import _get_token_counter

    monkeypatch.setenv("BUTLER_TOKEN_COUNTER", "tiktoken")
    monkeypatch.setitem(sys.modules, "tiktoken", None)

    counter = _get_token_counter()
    assert counter is not None
    rows = {r.component: r.reason for r in list_degradations()}
    assert "compaction_acl" in rows
    assert "tiktoken" in rows["compaction_acl"]

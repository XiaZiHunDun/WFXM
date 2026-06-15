"""Phase 4: WS-H trust polish — turn summary, memory sources, correction, /信任."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from butler.core.correction_intent import (
    extract_correction_content,
    is_correction_intent,
    try_handle_correction_intent,
)
from butler.core.memory_source_surface import (
    format_memory_sources_one_liner,
    format_memory_sources_report,
    snapshot_last_turn_memory_sources,
)
from butler.core.turn_summary_line import (
    build_turn_summary_line,
    maybe_prepend_turn_summary,
    turn_summary_enabled,
)
from butler.ops.owner_trust_surface import format_trust_owner_line, format_trust_report


def test_turn_summary_counts_reads_and_delegate(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_SESSION_TRANSCRIPT", "1")
    from butler.core.session_transcript import append_transcript_entry

    sk = "sk:phase4"
    for path in ("a.md", "b.md", "c.md"):
        append_transcript_entry(
            sk,
            "tool_action",
            {
                "tool": "read_file",
                "args_preview": json.dumps({"path": path}),
                "source": "loop",
            },
        )
    append_transcript_entry(
        sk,
        "tool_action",
        {"tool": "grep", "args_preview": "{}", "source": "loop"},
    )
    line = build_turn_summary_line(sk)
    assert line is not None
    assert "读了3文件" in line
    assert "检索1次" in line
    assert "无委派" in line


def test_maybe_prepend_turn_summary_opt_in(monkeypatch):
    monkeypatch.setenv("BUTLER_TURN_SUMMARY_LINE", "0")
    assert maybe_prepend_turn_summary("sk", "x" * 500) == "x" * 500

    monkeypatch.setenv("BUTLER_TURN_SUMMARY_LINE", "1")
    monkeypatch.setenv("BUTLER_TURN_SUMMARY_MIN_CHARS", "10")
    out = maybe_prepend_turn_summary("sk:empty", "y" * 20)
    assert out == "y" * 20


def test_turn_summary_enabled_default_off(monkeypatch):
    monkeypatch.delenv("BUTLER_TURN_SUMMARY_LINE", raising=False)
    assert turn_summary_enabled() is False


def test_memory_sources_one_liner_from_health():
    health = {
        "memory_experience_hits": 2,
        "skill_injection_mode": "fallback",
        "skill_injection_reason": "experience_hit",
        "memory_prefetch_retrieval_total": 3,
        "memory_prefetch_retrieval_used": 1,
    }
    line = format_memory_sources_one_liner(health)
    assert "经验2条" in line
    assert "Skill:fallback" in line
    assert "P_r 1/3" in line


def test_memory_sources_report_skipped():
    text = format_memory_sources_report({"memory_prefetch_skipped": "session_read_recall"})
    assert "已跳过" in text
    assert "session_read_recall" in text


def test_snapshot_last_turn_memory_sources():
    health: dict = {"memory_experience_hits": 1, "loop": {"skill_injection_mode": "ref_only"}}
    snapshot_last_turn_memory_sources(health)
    assert "memory_last_turn_sources" in health
    assert health["memory_last_turn_sources"]["memory_experience_hits"] == 1


def test_correction_intent_detect_and_extract():
    assert is_correction_intent("刚才那句不对：路径应是 LingWen1/docs")
    assert extract_correction_content("刚才那句不对：路径应是 LingWen1/docs") == "路径应是 LingWen1/docs"
    assert not is_correction_intent("/信任")


def test_correction_intent_persists(monkeypatch):
    orch = MagicMock()
    calls: list[dict] = []

    def fake_remember(**kwargs):
        calls.append(kwargs)
        return '{"ok": true}'

    monkeypatch.setattr(
        "butler.tools.memory_tools.tool_butler_remember",
        fake_remember,
    )
    monkeypatch.setattr(
        "butler.execution_context.use_execution_context",
        lambda *a, **k: MagicMock(__enter__=lambda s: None, __exit__=lambda s, *e: None),
    )
    out = try_handle_correction_intent(
        orch,
        "刚才说错了：不要读 projects/docs 夹具",
        session_key="wechat:u:1",
    )
    assert out is not None
    assert "已记录纠正" in out
    assert calls
    assert calls[0]["category"] == "correction"
    assert "projects/docs" in calls[0]["content"]
    assert "记忆来源" in out
    assert "/记忆来源" not in out


def test_format_trust_owner_line(monkeypatch):
    monkeypatch.setenv("BUTLER_SKILL_INJECTION_MODE", "fallback")
    monkeypatch.setattr(
        "butler.ops.health_report.collect_approval_stats_for_health",
        lambda sk: {"always_count": 1, "once_active_count": 0, "has_pending": False},
    )
    monkeypatch.setattr(
        "butler.ops.owner_trust_surface._boundary_warn_count",
        lambda: 2,
    )
    orch = MagicMock()
    line = format_trust_owner_line(
        orch,
        "sk",
        health={"skill_injection_mode": "fallback", "memory_experience_hits": 1},
    )
    assert "Skill:fallback" in line
    assert "边界warn2" in line


def test_format_trust_report_includes_sections(monkeypatch):
    monkeypatch.setenv("BUTLER_SKILL_INJECTION_MODE", "ref_only")
    monkeypatch.setattr(
        "butler.ops.health_report.collect_approval_stats_for_health",
        lambda sk: {"always_count": 0, "once_active_count": 1, "has_pending": True},
    )
    monkeypatch.setattr(
        "butler.ops.owner_trust_surface._boundary_warn_count",
        lambda: 0,
    )
    text = format_trust_report(MagicMock(), "sk", health={})
    assert "信任与透明度" in text
    assert "权限批准缓存" in text
    assert "待批准" in text

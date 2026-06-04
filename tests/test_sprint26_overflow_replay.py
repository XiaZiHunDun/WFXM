"""Sprint 26 P2-4.1: overflow_replay transcript 事件 + /诊断 续跑提示.

P2-4.1 gap 落地: 413 / payload_too_large 触发 reactive compact 时, 系统会
追加 [OVERFLOW REPLAY ...] 标记. 但当前 transcript 仅记录 4 类压缩事件
(scheduled/started/done/failed), 续跑行为对用户不可见.

覆盖:
  - record_overflow_replay 写入 transcript (type=overflow_replay, 含 source/preview/chars)
  - 默认值: source='context_compressor', content_preview='', replayed_chars=0
  - content_preview 截 80 字符
  - replayed_chars 负值钳到 0
  - summarize_compact_events 包含 overflow_replay key
  - format_transcript_diagnostic_lines 在 overflow_replay 计数 > 0 时输出
    '⚠️ 续跑提示' 行; 计数为 0 时不输出
"""

from __future__ import annotations

import pytest

from butler.core.session_transcript import (
    load_transcript_tail,
    record_overflow_replay,
)


# ── record_overflow_replay ──


class TestRecordOverflowReplay:
    def test_writes_event_to_transcript(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path / "home"))
        from butler.config import reload_butler_settings

        reload_butler_settings()
        sk = "sprint26:overflow:basic"
        record_overflow_replay(
            sk,
            source="context_compressor",
            content_preview="请帮我重写 README",
            replayed_chars=200,
        )
        rows = load_transcript_tail(sk, max_lines=10)
        assert len(rows) == 1
        assert rows[0].get("type") == "overflow_replay"
        assert rows[0].get("source") == "context_compressor"
        assert rows[0].get("content_preview") == "请帮我重写 README"
        assert rows[0].get("replayed_chars") == 200

    def test_default_source_and_empty_preview(self, tmp_path, monkeypatch):
        """不传参时: source='context_compressor', content_preview='', replayed_chars=0."""
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path / "home"))
        from butler.config import reload_butler_settings

        reload_butler_settings()
        sk = "sprint26:overflow:default"
        record_overflow_replay(sk)
        rows = load_transcript_tail(sk, max_lines=10)
        assert rows[0].get("source") == "context_compressor"
        assert rows[0].get("content_preview") == ""
        assert rows[0].get("replayed_chars") == 0

    def test_content_preview_truncated_to_80_chars(self, tmp_path, monkeypatch):
        """content_preview 应被截到 80 字符, 避免 transcript 文件膨胀."""
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path / "home"))
        from butler.config import reload_butler_settings

        reload_butler_settings()
        sk = "sprint26:overflow:trunc"
        long_text = "请" * 100  # 200 chars
        record_overflow_replay(sk, content_preview=long_text)
        rows = load_transcript_tail(sk, max_lines=10)
        assert len(rows[0].get("content_preview", "")) <= 80

    def test_replayed_chars_negative_clamped_to_zero(self, tmp_path, monkeypatch):
        """replayed_chars 负值应被 max(0, int()) 钳到 0."""
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path / "home"))
        from butler.config import reload_butler_settings

        reload_butler_settings()
        sk = "sprint26:overflow:neg"
        record_overflow_replay(sk, replayed_chars=-7)
        rows = load_transcript_tail(sk, max_lines=10)
        assert rows[0].get("replayed_chars") == 0

    def test_source_truncated_to_32_chars(self, tmp_path, monkeypatch):
        """source 应截到 32 字符 (沿用 record_compact_started 约定)."""
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path / "home"))
        from butler.config import reload_butler_settings

        reload_butler_settings()
        sk = "sprint26:overflow:src"
        long_source = "s" * 50
        record_overflow_replay(sk, source=long_source)
        rows = load_transcript_tail(sk, max_lines=10)
        assert len(rows[0].get("source", "")) <= 32


# ── transcript_diagnostics 集成 ──


class TestSummarizeCompactEvents:
    def test_includes_overflow_replay_key(self):
        """summarize_compact_events 应返回 6 key, 含 overflow_replay."""
        from butler.ops.transcript_diagnostics import summarize_compact_events

        rows = [
            {"type": "compact_scheduled"},
            {"type": "compact_started"},
            {"type": "compact_done"},
            {"type": "compact_failed"},
            {"type": "compact_boundary"},
            {"type": "overflow_replay"},
            {"type": "overflow_replay"},
        ]
        summary = summarize_compact_events(rows)
        assert summary["overflow_replay"] == 2
        # 旧 5 key 仍存在
        for k in (
            "compact_scheduled",
            "compact_started",
            "compact_done",
            "compact_failed",
            "compact_boundary",
        ):
            assert k in summary


class TestFormatDiagnosticLinesShowsOverflowReplay:
    def test_shows_warning_line_when_count_positive(self, tmp_path, monkeypatch):
        """overflow_replay 计数 > 0 时, 应输出 '⚠️ 续跑提示' 行."""
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path / "home"))
        from butler.config import reload_butler_settings

        reload_butler_settings()
        sk = "sprint26:diag:show"
        record_overflow_replay(
            sk,
            content_preview="继续完成 refactor",
            replayed_chars=50,
        )

        from butler.ops.transcript_diagnostics import (
            format_transcript_diagnostic_lines,
        )

        lines = format_transcript_diagnostic_lines(sk)
        warn_line = next(
            (ln for ln in lines if "续跑" in ln or "overflow_replay" in ln.lower()),
            None,
        )
        assert warn_line is not None

    def test_no_warning_line_when_count_zero(self, tmp_path, monkeypatch):
        """overflow_replay 计数 = 0 时, 不应输出 '⚠️ 续跑提示' 行 (避免无谓告警)."""
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path / "home"))
        from butler.config import reload_butler_settings

        reload_butler_settings()
        sk = "sprint26:diag:no-show"
        # 只写 scheduled, 不写 overflow_replay
        from butler.core.session_transcript import record_compact_scheduled

        record_compact_scheduled(sk, source="t")

        from butler.ops.transcript_diagnostics import (
            format_transcript_diagnostic_lines,
        )

        lines = format_transcript_diagnostic_lines(sk)
        warn_line = next(
            (ln for ln in lines if "续跑" in ln or "overflow_replay" in ln.lower()),
            None,
        )
        assert warn_line is None

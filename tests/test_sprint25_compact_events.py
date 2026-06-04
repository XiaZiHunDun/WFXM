"""Sprint 25 P2-4.2: compact_started + compact_failed 事件类型.

P2-4.2 gap 落地: record_compact_scheduled / record_compact_done / compact_boundary
之外补齐 2 类事件, 让 /诊断 + transcript 能区分"压缩中"与"压缩失败".

覆盖:
  - record_compact_started 写入 transcript (type=compact_started, 含 source/trigger)
  - record_compact_failed 写入 transcript (type=compact_failed, 含 source/reason/iteration)
  - summarize_compact_events 包含 4 个 key
  - format_transcript_diagnostic_lines 输出行展示 started/failed 计数
  - 边界: source 截 32 字符, reason 截 64 字符 (与既有 record_* 同约束)
"""

from __future__ import annotations

import pytest

from butler.core.session_transcript import (
    load_transcript_tail,
    record_compact_failed,
    record_compact_scheduled,
    record_compact_started,
    transcript_path,
)


# ── record_compact_started ──


class TestRecordCompactStarted:
    def test_writes_event_to_transcript(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path / "home"))
        from butler.config import reload_butler_settings

        reload_butler_settings()
        sk = "sprint25:started"
        record_compact_started(sk, source="reactive", trigger="overflow")
        rows = load_transcript_tail(sk, max_lines=10)
        assert len(rows) == 1
        assert rows[0].get("type") == "compact_started"
        assert rows[0].get("source") == "reactive"
        assert rows[0].get("trigger") == "overflow"
        assert transcript_path(sk).is_file()

    def test_default_source_and_trigger(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path / "home"))
        from butler.config import reload_butler_settings

        reload_butler_settings()
        sk = "sprint25:started:default"
        record_compact_started(sk)
        rows = load_transcript_tail(sk, max_lines=10)
        assert rows[0].get("source") == "context"
        assert rows[0].get("trigger") == "threshold"

    def test_source_truncated_to_32_chars(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path / "home"))
        from butler.config import reload_butler_settings

        reload_butler_settings()
        sk = "sprint25:started:trunc"
        long_source = "x" * 60
        record_compact_started(sk, source=long_source)
        rows = load_transcript_tail(sk, max_lines=10)
        # record_compact_scheduled 用 str(source or "context")[:32]
        # 起始 "x" 32 字符 + 后续被截断
        assert len(rows[0].get("source", "")) <= 32

    def test_trigger_truncated_to_32_chars(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path / "home"))
        from butler.config import reload_butler_settings

        reload_butler_settings()
        sk = "sprint25:started:trunc"
        long_trigger = "t" * 50
        record_compact_started(sk, trigger=long_trigger)
        rows = load_transcript_tail(sk, max_lines=10)
        assert len(rows[0].get("trigger", "")) <= 32

    def test_event_does_not_interfere_with_scheduled_done(self, tmp_path, monkeypatch):
        """started 事件与 scheduled/done 共存于同一 transcript, 顺序保持."""
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path / "home"))
        from butler.config import reload_butler_settings

        reload_butler_settings()
        sk = "sprint25:started:coexist"
        record_compact_scheduled(sk, source="test")
        record_compact_started(sk, source="test")
        # 跳过 compact_done, 模拟失败路径
        rows = load_transcript_tail(sk, max_lines=10)
        types = [r.get("type") for r in rows]
        assert types == ["compact_scheduled", "compact_started"]


# ── record_compact_failed ──


class TestRecordCompactFailed:
    def test_writes_event_to_transcript(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path / "home"))
        from butler.config import reload_butler_settings

        reload_butler_settings()
        sk = "sprint25:failed"
        record_compact_failed(
            sk,
            source="reactive",
            reason="compress_error",
            iteration=3,
        )
        rows = load_transcript_tail(sk, max_lines=10)
        assert len(rows) == 1
        assert rows[0].get("type") == "compact_failed"
        assert rows[0].get("source") == "reactive"
        assert rows[0].get("reason") == "compress_error"
        assert rows[0].get("iteration") == 3

    def test_default_values(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path / "home"))
        from butler.config import reload_butler_settings

        reload_butler_settings()
        sk = "sprint25:failed:default"
        record_compact_failed(sk)
        rows = load_transcript_tail(sk, max_lines=10)
        assert rows[0].get("source") == "context"
        assert rows[0].get("reason") == "unknown"
        assert rows[0].get("iteration") == 0

    def test_reason_truncated_to_64_chars(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path / "home"))
        from butler.config import reload_butler_settings

        reload_butler_settings()
        sk = "sprint25:failed:trunc"
        long_reason = "r" * 80
        record_compact_failed(sk, reason=long_reason)
        rows = load_transcript_tail(sk, max_lines=10)
        assert len(rows[0].get("reason", "")) <= 64

    def test_iteration_negative_clamped_to_zero(self, tmp_path, monkeypatch):
        """负值 iteration 应被 max(0, int()) 钳到 0 (沿用 record_compact_scheduled 风格)."""
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path / "home"))
        from butler.config import reload_butler_settings

        reload_butler_settings()
        sk = "sprint25:failed:neg"
        record_compact_failed(sk, iteration=-5)
        rows = load_transcript_tail(sk, max_lines=10)
        assert rows[0].get("iteration") == 0

    def test_source_truncated_to_32_chars(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path / "home"))
        from butler.config import reload_butler_settings

        reload_butler_settings()
        sk = "sprint25:failed:src"
        long_source = "s" * 50
        record_compact_failed(sk, source=long_source)
        rows = load_transcript_tail(sk, max_lines=10)
        assert len(rows[0].get("source", "")) <= 32


# ── transcript_diagnostics 集成 ──


class TestSummarizeCompactEvents:
    def test_includes_started_and_failed_keys(self):
        """summarize_compact_events 应返回 4 key, 含 started/failed."""
        from butler.ops.transcript_diagnostics import summarize_compact_events

        rows = [
            {"type": "compact_scheduled"},
            {"type": "compact_started"},
            {"type": "compact_done"},
            {"type": "compact_failed"},
            {"type": "compact_boundary"},
            {"type": "compact_scheduled"},
        ]
        summary = summarize_compact_events(rows)
        assert summary["compact_scheduled"] == 2
        assert summary["compact_started"] == 1
        assert summary["compact_done"] == 1
        assert summary["compact_failed"] == 1
        assert summary["compact_boundary"] == 1

    def test_empty_rows_returns_zero_counts(self):
        from butler.ops.transcript_diagnostics import summarize_compact_events

        summary = summarize_compact_events([])
        assert summary == {
            "compact_scheduled": 0,
            "compact_started": 0,
            "compact_done": 0,
            "compact_failed": 0,
            "compact_boundary": 0,
        }


class TestFormatDiagnosticLinesShowsStartedFailed:
    def test_output_line_includes_started_and_failed_counts(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path / "home"))
        from butler.config import reload_butler_settings

        reload_butler_settings()
        sk = "sprint25:diag"
        record_compact_scheduled(sk, source="t")
        record_compact_started(sk, source="t")
        record_compact_failed(sk, source="t", reason="exhausted")
        record_compact_failed(sk, source="t", reason="error")

        from butler.ops.transcript_diagnostics import (
            format_transcript_diagnostic_lines,
        )

        lines = format_transcript_diagnostic_lines(sk)
        # 第一行是压缩摘要, 应含 started/failed 计数
        compress_line = next(
            (ln for ln in lines if ln.startswith("Transcript:") and "压缩" in ln),
            None,
        )
        assert compress_line is not None
        # 新格式约定: "压缩 X/Y 完成 · started=A · failed=B" 或类似
        assert "started" in compress_line
        assert "failed" in compress_line
        # scheduled=1, done=0, started=1, failed=2
        assert "1" in compress_line
        assert "2" in compress_line

    def test_output_line_when_no_failures_still_shows_failed_zero(
        self, tmp_path, monkeypatch
    ):
        """无失败时输出行仍展示 'failed=0' (统一契约, 始终显示 4 个计数)."""
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path / "home"))
        from butler.config import reload_butler_settings

        reload_butler_settings()
        sk = "sprint25:diag:clean"
        record_compact_scheduled(sk, source="t")
        record_compact_started(sk, source="t")

        from butler.ops.transcript_diagnostics import (
            format_transcript_diagnostic_lines,
        )

        lines = format_transcript_diagnostic_lines(sk)
        compress_line = next(
            (ln for ln in lines if ln.startswith("Transcript:") and "压缩" in ln),
            None,
        )
        assert compress_line is not None
        assert "started" in compress_line
        assert "failed" in compress_line
        # failed=0 应出现
        assert "failed=0" in compress_line

"""Sprint 16 TST-11-11: schedule 直测补全.

之前仅 2 个 e2e-ish 测试 (consistency_weekly, mutating_gated), 核心 helper 无直测.
覆盖:
  - job_is_due: 空 schedule / 错 cron / 准点 / croniter 缺失
  - format_schedule_hint: 空 / 非空
  - next_run_iso: 空 / 错 cron / 准点 / croniter 缺失
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from butler.runtime import schedule


# ── job_is_due ──


class TestJobIsDue:
    def test_empty_schedule_returns_false(self):
        assert schedule.job_is_due("") is False

    def test_whitespace_only_schedule_returns_false(self):
        assert schedule.job_is_due("   ") is False

    def test_invalid_cron_returns_false(self):
        assert schedule.job_is_due("not a cron") is False

    def test_returns_true_when_at_minute_boundary(self):
        # 假设 now 处于某个 cron fire 时间, 验证 prev 在 90s 内
        # 用一个特定 now, 选一个能 fire 的 cron
        # Monday 00:00 UTC fire for "0 0 * * 1"
        from datetime import timedelta

        # 找一个最近的 Monday 00:00:30
        now = datetime(2026, 6, 1, 0, 0, 30, tzinfo=timezone.utc)  # 6/1 是 Monday
        assert schedule.job_is_due("0 0 * * 1", now=now) is True

    def test_returns_false_far_from_cron(self):
        # Tuesday 12:00, 距 Monday 00:00 已超 36 小时
        now = datetime(2026, 6, 2, 12, 0, 0, tzinfo=timezone.utc)
        assert schedule.job_is_due("0 0 * * 1", now=now) is False

    def test_returns_false_when_croniter_missing(self, monkeypatch):
        monkeypatch.setattr(schedule, "croniter", None)
        assert schedule.job_is_due("* * * * *") is False

    def test_naive_datetime_prev_assumes_utc(self):
        # croniter 偶尔返回 naive datetime, 应自动补 UTC
        # 这通过内部逻辑, 用一个相对宽松的 now 测试
        now = datetime(2026, 6, 1, 0, 0, 5, tzinfo=timezone.utc)
        # 不应抛异常
        result = schedule.job_is_due("0 0 * * 1", now=now)
        assert isinstance(result, bool)


# ── format_schedule_hint ──


class TestFormatScheduleHint:
    def test_empty_returns_manual_label(self):
        assert schedule.format_schedule_hint("") == "（手动）"

    def test_whitespace_returns_manual_label(self):
        assert schedule.format_schedule_hint("   ") == "（手动）"

    def test_non_empty_returns_as_is(self):
        assert schedule.format_schedule_hint("0 0 * * *") == "0 0 * * *"

    def test_strips_whitespace(self):
        assert schedule.format_schedule_hint("  0 0 * * *  ") == "0 0 * * *"


# ── next_run_iso ──


class TestNextRunIso:
    def test_empty_returns_none(self):
        assert schedule.next_run_iso("") is None

    def test_invalid_cron_returns_none(self):
        assert schedule.next_run_iso("not a cron") is None

    def test_returns_none_when_croniter_missing(self, monkeypatch):
        monkeypatch.setattr(schedule, "croniter", None)
        assert schedule.next_run_iso("* * * * *") is None

    def test_returns_iso_string_for_valid_cron(self):
        result = schedule.next_run_iso("0 0 * * 1")  # every Monday 00:00
        assert result is not None
        # ISO 8601 格式
        assert "T" in result
        assert result.endswith("+00:00") or result.endswith("Z")

    def test_naive_next_assumes_utc(self):
        result = schedule.next_run_iso("0 0 * * 1")
        # 不应抛异常, 内部应处理 naive datetime
        assert result is not None

    def test_iso_can_be_parsed_back(self):
        from datetime import datetime
        result = schedule.next_run_iso("0 0 * * 1")
        # 应能被 fromisoformat 解析
        parsed = datetime.fromisoformat(result)
        assert parsed.tzinfo is not None

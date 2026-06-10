"""Tests for butler.tools.habits — daily habit tracker."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

os.environ.setdefault("BUTLER_MODEL", "test-dummy")

from butler.tools.habits import (
    _CN_TZ,
    format_habits_for_wechat,
    register_habit_tools,
    tool_habit_checkin,
    tool_habit_create,
    tool_habit_delete,
    tool_habit_list,
    tool_habit_stats,
)


def _today() -> str:
    return datetime.now(_CN_TZ).strftime("%Y-%m-%d")


def _yesterday() -> str:
    return (datetime.now(_CN_TZ) - timedelta(days=1)).strftime("%Y-%m-%d")


@pytest.fixture(autouse=True)
def _tmp_habits(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    habits_dir = tmp_path / "habits"
    habits_dir.mkdir()
    checkins_dir = habits_dir / "checkins"
    checkins_dir.mkdir()
    monkeypatch.setattr("butler.tools.habits._store.storage_dir", lambda: habits_dir)
    monkeypatch.setattr("butler.tools.habits._checkin_store.storage_dir", lambda: checkins_dir)
    monkeypatch.setenv("BUTLER_HABITS_ENABLED", "1")
    yield habits_dir


class TestHabitCreate:
    def test_basic_create(self):
        data = json.loads(tool_habit_create(name="喝水"))
        assert data["ok"] is True
        assert data["name"] == "喝水"
        assert data["frequency"] == "daily"
        assert data["target_count"] == 1

    def test_create_weekly(self):
        data = json.loads(tool_habit_create(name="运动", frequency="weekly", target_count=3))
        assert data["frequency"] == "weekly"
        assert data["target_count"] == 3

    def test_create_empty_name(self):
        data = json.loads(tool_habit_create(name=""))
        assert data["ok"] is False

    def test_create_duplicate(self):
        tool_habit_create(name="跑步")
        data = json.loads(tool_habit_create(name="跑步"))
        assert data["ok"] is False
        assert "already exists" in data["error"]

    def test_create_disabled(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("BUTLER_HABITS_ENABLED", "0")
        data = json.loads(tool_habit_create(name="x"))
        assert data["ok"] is False


class TestHabitCheckin:
    def test_checkin_by_id(self):
        hid = json.loads(tool_habit_create(name="喝水"))["habit_id"]
        data = json.loads(tool_habit_checkin(habit_id=hid))
        assert data["ok"] is True
        assert data["habit"] == "喝水"
        assert data["date"] == _today()
        assert data["streak"] >= 1

    def test_checkin_by_name(self):
        tool_habit_create(name="跑步")
        data = json.loads(tool_habit_checkin(habit_id="跑步"))
        assert data["ok"] is True
        assert data["habit"] == "跑步"

    def test_checkin_by_prefix(self):
        hid = json.loads(tool_habit_create(name="冥想"))["habit_id"]
        data = json.loads(tool_habit_checkin(habit_id=hid[:4]))
        assert data["ok"] is True

    def test_checkin_accumulates(self):
        hid = json.loads(tool_habit_create(name="喝水"))["habit_id"]
        tool_habit_checkin(habit_id=hid, count=3)
        data = json.loads(tool_habit_checkin(habit_id=hid, count=2))
        assert data["count"] == 5

    def test_checkin_with_note(self):
        hid = json.loads(tool_habit_create(name="跑步"))["habit_id"]
        data = json.loads(tool_habit_checkin(habit_id=hid, note="5公里"))
        assert data["ok"] is True

    def test_checkin_specific_date(self):
        hid = json.loads(tool_habit_create(name="读书"))["habit_id"]
        data = json.loads(tool_habit_checkin(habit_id=hid, date=_yesterday()))
        assert data["date"] == _yesterday()

    def test_checkin_not_found(self):
        data = json.loads(tool_habit_checkin(habit_id="nope"))
        assert data["ok"] is False

    def test_streak_consecutive(self):
        hid = json.loads(tool_habit_create(name="跑步"))["habit_id"]
        tool_habit_checkin(habit_id=hid, date=_yesterday())
        data = json.loads(tool_habit_checkin(habit_id=hid, date=_today()))
        assert data["streak"] >= 2


class TestHabitStats:
    def test_stats_all_empty(self):
        data = json.loads(tool_habit_stats())
        assert data["ok"] is True
        assert data["habits"] == []

    def test_stats_all(self):
        hid = json.loads(tool_habit_create(name="喝水"))["habit_id"]
        tool_habit_checkin(habit_id=hid)
        data = json.loads(tool_habit_stats())
        assert len(data["habits"]) == 1
        assert data["habits"][0]["today_done"] is True
        assert data["habits"][0]["streak"] >= 1

    def test_stats_single(self):
        hid = json.loads(tool_habit_create(name="跑步"))["habit_id"]
        tool_habit_checkin(habit_id=hid)
        data = json.loads(tool_habit_stats(habit_id=hid))
        assert data["ok"] is True
        assert data["name"] == "跑步"
        assert data["today_done"] is True

    def test_stats_not_found(self):
        data = json.loads(tool_habit_stats(habit_id="nope"))
        assert data["ok"] is False


class TestHabitList:
    def test_list_empty(self):
        data = json.loads(tool_habit_list())
        assert data["active_count"] == 0

    def test_list_active(self):
        tool_habit_create(name="A")
        tool_habit_create(name="B")
        data = json.loads(tool_habit_list())
        assert data["active_count"] == 2


class TestHabitDelete:
    def test_archive_habit(self):
        hid = json.loads(tool_habit_create(name="跑步"))["habit_id"]
        data = json.loads(tool_habit_delete(habit_id=hid))
        assert data["ok"] is True
        assert data["name"] == "跑步"
        list_data = json.loads(tool_habit_list())
        assert list_data["active_count"] == 0
        assert list_data["archived_count"] == 1

    def test_delete_not_found(self):
        data = json.loads(tool_habit_delete(habit_id="nope"))
        assert data["ok"] is False

    def test_archived_not_recreatable(self):
        """Archived habit should not block re-creation with same name."""
        hid = json.loads(tool_habit_create(name="跑步"))["habit_id"]
        tool_habit_delete(habit_id=hid)
        data = json.loads(tool_habit_create(name="跑步"))
        assert data["ok"] is True


class TestWeChat:
    def test_wechat_empty(self):
        result = format_habits_for_wechat()
        assert "暂无习惯" in result

    def test_wechat_dashboard(self):
        hid = json.loads(tool_habit_create(name="喝水"))["habit_id"]
        tool_habit_checkin(habit_id=hid)
        result = format_habits_for_wechat()
        assert "喝水" in result
        assert "✅" in result

    def test_wechat_create(self):
        result = format_habits_for_wechat("创建 冥想")
        assert "已创建" in result
        assert "冥想" in result

    def test_wechat_checkin(self):
        tool_habit_create(name="跑步")
        result = format_habits_for_wechat("打 跑步")
        assert "已打卡" in result

    def test_wechat_disabled(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("BUTLER_HABITS_ENABLED", "0")
        assert "未启用" in format_habits_for_wechat()


class TestHabitCreateEdgeCases:
    def test_create_invalid_frequency(self):
        data = json.loads(tool_habit_create(name="test", frequency="monthly"))
        assert data["ok"] is True
        assert data["frequency"] == "daily"

    def test_create_zero_target(self):
        data = json.loads(tool_habit_create(name="test", target_count=0))
        assert data["target_count"] == 1

    def test_create_case_insensitive_duplicate(self):
        tool_habit_create(name="跑步")
        data = json.loads(tool_habit_create(name="跑步"))
        assert data["ok"] is False


class TestStreakEdgeCases:
    def test_streak_broken(self):
        hid = json.loads(tool_habit_create(name="test"))["habit_id"]
        today = datetime.now(_CN_TZ).date()
        tool_habit_checkin(habit_id=hid, date=(today - timedelta(days=3)).isoformat())
        tool_habit_checkin(habit_id=hid, date=(today - timedelta(days=2)).isoformat())
        # day -1 missing (streak broken)
        tool_habit_checkin(habit_id=hid, date=today.isoformat())
        data = json.loads(tool_habit_stats(habit_id=hid))
        assert data["streak"] == 1

    def test_streak_today_only(self):
        hid = json.loads(tool_habit_create(name="test"))["habit_id"]
        tool_habit_checkin(habit_id=hid)
        data = json.loads(tool_habit_stats(habit_id=hid))
        assert data["streak"] == 1

    def test_streak_no_checkins(self):
        hid = json.loads(tool_habit_create(name="test"))["habit_id"]
        data = json.loads(tool_habit_stats(habit_id=hid))
        assert data["streak"] == 0


class TestCompletionRate:
    def test_rate_all_done(self):
        from butler.tools.habits import _calc_completion_rate
        hid = json.loads(tool_habit_create(name="test"))["habit_id"]
        today = datetime.now(_CN_TZ).date()
        for i in range(7):
            d = (today - timedelta(days=i)).isoformat()
            tool_habit_checkin(habit_id=hid, date=d)
        rate = _calc_completion_rate(hid, 7)
        assert rate == 100.0

    def test_rate_partial(self):
        from butler.tools.habits import _calc_completion_rate
        hid = json.loads(tool_habit_create(name="test"))["habit_id"]
        today = datetime.now(_CN_TZ).date()
        for i in range(3):
            d = (today - timedelta(days=i)).isoformat()
            tool_habit_checkin(habit_id=hid, date=d)
        rate = _calc_completion_rate(hid, 7)
        assert 40.0 <= rate <= 50.0


class TestWeeklyHabits:
    def test_weekly_count(self):
        from butler.tools.habits import _calc_weekly_count
        hid = json.loads(tool_habit_create(name="运动", frequency="weekly", target_count=3))["habit_id"]
        today = datetime.now(_CN_TZ).date()
        week_start = today - timedelta(days=today.weekday())
        tool_habit_checkin(habit_id=hid, date=week_start.isoformat())
        tool_habit_checkin(habit_id=hid, date=(week_start + timedelta(days=2)).isoformat())
        count = _calc_weekly_count(hid)
        assert count == 2

    def test_weekly_stats_include_weekly_fields(self):
        hid = json.loads(tool_habit_create(name="运动", frequency="weekly", target_count=3))["habit_id"]
        tool_habit_checkin(habit_id=hid)
        data = json.loads(tool_habit_stats())
        h = data["habits"][0]
        assert "weekly_count" in h
        assert "weekly_target" in h
        assert h["weekly_target"] == 3


class TestHabitCheckinEdgeCases:
    def test_checkin_invalid_date(self):
        hid = json.loads(tool_habit_create(name="test"))["habit_id"]
        data = json.loads(tool_habit_checkin(habit_id=hid, date="bad-date"))
        assert data["ok"] is True
        assert data["date"] == _today()

    def test_checkin_note_accumulates(self):
        from butler.tools.habits import _get_checkin
        hid = json.loads(tool_habit_create(name="test"))["habit_id"]
        tool_habit_checkin(habit_id=hid, note="first")
        tool_habit_checkin(habit_id=hid, note="second")
        ci = _get_checkin(hid, _today())
        assert "first" in ci["note"]
        assert "second" in ci["note"]


class TestWeChatEdgeCases:
    def test_wechat_create_no_name_fallback(self):
        """No-space subcommand falls back to dashboard."""
        result = format_habits_for_wechat("创建")
        assert "暂无习惯" in result or "习惯" in result

    def test_wechat_checkin_not_found(self):
        result = format_habits_for_wechat("打 不存在的习惯")
        assert "失败" in result or "not found" in result.lower()

    def test_wechat_dashboard_undone(self):
        tool_habit_create(name="跑步")
        result = format_habits_for_wechat()
        assert "⬜" in result
        assert "0/1" in result

    def test_wechat_streak_display(self):
        hid = json.loads(tool_habit_create(name="跑步"))["habit_id"]
        today = datetime.now(_CN_TZ).date()
        for i in range(3):
            tool_habit_checkin(habit_id=hid, date=(today - timedelta(days=i)).isoformat())
        result = format_habits_for_wechat()
        assert "🔥" in result
        assert "3天" in result

    def test_wechat_multiple_habits(self):
        h1 = json.loads(tool_habit_create(name="跑步"))["habit_id"]
        tool_habit_create(name="读书")
        tool_habit_checkin(habit_id=h1)
        result = format_habits_for_wechat()
        assert "跑步" in result
        assert "读书" in result
        assert "1/2" in result


class TestRegistration:
    def test_register(self):
        registered = {}
        register_habit_tools(lambda name, **kw: registered.update({name: kw}))
        expected = {"habit_create", "habit_checkin", "habit_stats", "habit_list", "habit_update", "habit_delete"}
        assert set(registered.keys()) == expected
        for info in registered.values():
            assert info.get("toolset") == "habits"

    def test_register_disabled(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("BUTLER_HABITS_ENABLED", "0")
        registered = {}
        register_habit_tools(lambda name, **kw: registered.update({name: kw}))
        assert len(registered) == 0

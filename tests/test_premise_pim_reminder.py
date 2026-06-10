"""Premise P-PIM1/P-PIM3 verification: Reminder push reliability and PIM injection guard.

Validates:
  - One-shot reminders transition to 'fired' after poll
  - Recurring reminders reschedule (no stacking)
  - poll_due_reminders returns only due items
  - Cron aliases resolve correctly
  - PIM category/enum injection is blocked (closed sets)

Theoretical reference: 命题 2.13 (周期提醒不堆积), 命题 2.4 (提醒不丢失), §2.3
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


_CN_TZ = timezone(timedelta(hours=8))


@pytest.fixture(autouse=True)
def _isolate_reminders(tmp_path, monkeypatch):
    """Redirect reminder storage to a temp directory."""
    home = tmp_path / ".butler"
    home.mkdir(exist_ok=True)
    monkeypatch.setenv("BUTLER_HOME", str(home))
    from butler.config import reload_butler_settings
    reload_butler_settings()
    yield


class TestOneShotReminder:
    def test_oneshot_fires_when_due(self):
        from butler.tools.reminder import _save_reminder, poll_due_reminders, _reminders_dir

        _reminders_dir().mkdir(parents=True, exist_ok=True)
        past_ts = time.time() - 10
        reminder = {
            "id": "oneshot01",
            "message": "Test",
            "due_ts": past_ts,
            "due_human": "2026-06-01 09:00",
            "created_ts": past_ts - 100,
            "status": "pending",
        }
        _save_reminder(reminder)

        fired = poll_due_reminders()
        assert len(fired) == 1
        assert fired[0]["id"] == "oneshot01"
        assert fired[0]["status"] == "fired"

    def test_oneshot_transitions_to_fired(self):
        from butler.tools.reminder import _save_reminder, poll_due_reminders, _reminders_dir

        _reminders_dir().mkdir(parents=True, exist_ok=True)
        _save_reminder({
            "id": "os_trans",
            "message": "Trans test",
            "due_ts": time.time() - 5,
            "due_human": "2026-06-01 09:00",
            "created_ts": time.time() - 100,
            "status": "pending",
        })

        poll_due_reminders()

        path = _reminders_dir() / "os_trans.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["status"] == "fired"

    def test_future_reminder_not_fired(self):
        from butler.tools.reminder import _save_reminder, poll_due_reminders, _reminders_dir

        _reminders_dir().mkdir(parents=True, exist_ok=True)
        _save_reminder({
            "id": "future01",
            "message": "Later",
            "due_ts": time.time() + 3600,
            "due_human": "2026-06-02 09:00",
            "created_ts": time.time(),
            "status": "pending",
        })

        fired = poll_due_reminders()
        assert len(fired) == 0

    def test_already_fired_not_refired(self):
        from butler.tools.reminder import _save_reminder, poll_due_reminders, _reminders_dir

        _reminders_dir().mkdir(parents=True, exist_ok=True)
        _save_reminder({
            "id": "norefire",
            "message": "Done",
            "due_ts": time.time() - 10,
            "due_human": "2026-06-01 08:00",
            "created_ts": time.time() - 200,
            "status": "fired",
            "fired_ts": time.time() - 5,
        })

        fired = poll_due_reminders()
        assert len(fired) == 0


class TestRecurringReminder:
    def test_recurring_reschedules_after_fire(self):
        from butler.tools.reminder import _save_reminder, poll_due_reminders, _reminders_dir

        _reminders_dir().mkdir(parents=True, exist_ok=True)
        now = time.time()
        _save_reminder({
            "id": "cron01",
            "message": "Daily standup",
            "cron": "0 9 * * *",
            "due_ts": now - 10,
            "due_human": "2026-06-01 09:00",
            "created_ts": now - 100,
            "status": "pending",
            "recurring": True,
            "fire_count": 0,
        })

        fired = poll_due_reminders()
        assert len(fired) == 1

        path = _reminders_dir() / "cron01.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["status"] == "pending"
        assert data["fire_count"] == 1
        assert data["due_ts"] > now

    def test_recurring_does_not_stack(self):
        """Multiple polls should not fire the same recurring reminder twice."""
        from butler.tools.reminder import _save_reminder, poll_due_reminders, _reminders_dir

        _reminders_dir().mkdir(parents=True, exist_ok=True)
        now = time.time()
        _save_reminder({
            "id": "nostack",
            "message": "Check",
            "cron": "0 * * * *",
            "due_ts": now - 10,
            "due_human": "2026-06-01 10:00",
            "created_ts": now - 100,
            "status": "pending",
            "recurring": True,
            "fire_count": 0,
        })

        fired1 = poll_due_reminders()
        assert len(fired1) == 1

        fired2 = poll_due_reminders()
        assert len(fired2) == 0

        path = _reminders_dir() / "nostack.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["fire_count"] == 1


class TestCronAliases:
    def test_daily_alias(self):
        from butler.tools.reminder import _parse_cron_schedule
        assert _parse_cron_schedule("每天") == "0 9 * * *"
        assert _parse_cron_schedule("daily") == "0 9 * * *"

    def test_weekdays_alias(self):
        from butler.tools.reminder import _parse_cron_schedule
        assert _parse_cron_schedule("工作日") == "0 9 * * 1-5"
        assert _parse_cron_schedule("weekdays") == "0 9 * * 1-5"

    def test_natural_time(self):
        from butler.tools.reminder import _parse_cron_schedule
        result = _parse_cron_schedule("每天 8:30")
        assert result == "30 8 * * *"

    def test_raw_cron(self):
        from butler.tools.reminder import _parse_cron_schedule
        result = _parse_cron_schedule("0 9 * * 1-5")
        assert result == "0 9 * * 1-5"

    def test_invalid_returns_none(self):
        from butler.tools.reminder import _parse_cron_schedule
        assert _parse_cron_schedule("not a cron") is None


class TestPIMEnumClosure:
    """P-PIM3: Verify PIM enums are closed sets — no injection via string input."""

    def test_contacts_category_injection_blocked(self):
        from butler.tools.contacts import _normalize_category
        assert _normalize_category("'; DROP TABLE") == "personal"

    def test_memo_priority_injection_blocked(self):
        from butler.tools.memo import _normalize_priority
        assert _normalize_priority("admin") == "normal"

    def test_memo_status_injection_blocked(self):
        from butler.tools.memo import _normalize_status
        assert _normalize_status("superuser") == "active"

    def test_expense_direction_injection_blocked(self):
        from butler.tools.expense import _normalize_direction
        assert _normalize_direction("hack") == "expense"

    def test_habits_frequency_defaults(self):
        from butler.tools.habits import _VALID_FREQUENCIES
        assert "monthly" not in _VALID_FREQUENCIES

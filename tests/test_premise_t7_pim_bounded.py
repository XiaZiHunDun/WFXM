"""Premise T7 verification: PIM TenantStore bounded storage.

Validates:
  - Each PIM module enforces its hardcoded record limit
  - Content fields are truncated to documented limits
  - Category/priority enums are closed sets
  - Checkin accumulation (idempotency) works correctly

Theoretical reference: T7' (PIM 数据有界性), §2.3, §5 T7'
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
from pathlib import Path
from unittest import mock

import pytest


@pytest.fixture(autouse=True)
def _isolate_tenant(tmp_path, monkeypatch):
    """Redirect TenantStore to a temp directory for each test."""
    home = tmp_path / ".butler"
    home.mkdir(exist_ok=True)
    monkeypatch.setenv("BUTLER_HOME", str(home))
    monkeypatch.setenv("BUTLER_TENANT", "test_t7")
    monkeypatch.setenv("BUTLER_CONTACTS_ENABLED", "1")
    monkeypatch.setenv("BUTLER_MEMO_ENABLED", "1")
    monkeypatch.setenv("BUTLER_EXPENSE_ENABLED", "1")
    monkeypatch.setenv("BUTLER_HABITS_ENABLED", "1")
    from butler.config import reload_butler_settings
    from butler.tools._file_cache import clear_cache
    reload_butler_settings()
    clear_cache()
    yield
    clear_cache()


# ── Contacts bounded ───────────────────────────────────────────

class TestContactsBounded:
    def test_max_contacts_constant(self):
        from butler.tools.contacts import _MAX_CONTACTS
        assert _MAX_CONTACTS == 500

    def test_add_rejects_at_limit(self, tmp_path, monkeypatch):
        from butler.tools.contacts import tool_contact_add, _contacts_dir

        d = _contacts_dir()
        d.mkdir(parents=True, exist_ok=True)
        for i in range(500):
            (d / f"fake{i:04d}.json").write_text(
                json.dumps({"id": f"fake{i:04d}", "name": f"Person{i}"}),
                encoding="utf-8",
            )

        from butler.tools._file_cache import clear_cache
        clear_cache()

        result = json.loads(tool_contact_add(name="Overflow"))
        assert result["ok"] is False
        assert "limit" in result["error"].lower() or "500" in result["error"]

    def test_notes_truncated_at_500(self):
        from butler.tools.contacts import tool_contact_add
        long_notes = "x" * 1000
        result = json.loads(tool_contact_add(name="TruncTest", notes=long_notes))
        assert result["ok"] is True

        from butler.tools.contacts import _store
        contact = _store.load_one(result["contact_id"])
        assert len(contact["notes"]) <= 500

    def test_phones_capped_at_5(self):
        from butler.tools.contacts import tool_contact_add, _store
        phones = [f"1380000{i:04d}" for i in range(10)]
        result = json.loads(tool_contact_add(name="PhoneTest", phone=phones))
        assert result["ok"] is True
        contact = _store.load_one(result["contact_id"])
        assert len(contact["phone"]) <= 5

    def test_tags_capped_at_10(self):
        from butler.tools.contacts import tool_contact_add, _store
        tags = [f"tag{i}" for i in range(20)]
        result = json.loads(tool_contact_add(name="TagTest", tags=tags))
        assert result["ok"] is True
        contact = _store.load_one(result["contact_id"])
        assert len(contact["tags"]) <= 10

    def test_tag_length_capped_at_30(self):
        from butler.tools.contacts import tool_contact_add, _store
        result = json.loads(tool_contact_add(name="LongTag", tags=["a" * 100]))
        assert result["ok"] is True
        contact = _store.load_one(result["contact_id"])
        assert len(contact["tags"][0]) <= 30

    def test_category_enum_closed(self):
        from butler.tools.contacts import _VALID_CATEGORIES
        assert "personal" in _VALID_CATEGORIES
        assert "invalid_cat" not in _VALID_CATEGORIES

    def test_invalid_category_defaults(self):
        from butler.tools.contacts import _normalize_category
        assert _normalize_category("nonsense") == "personal"
        assert _normalize_category("work") == "work"


# ── Memo bounded ──────────────────────────────────────────────

class TestMemoBounded:
    def test_max_active_constant(self):
        from butler.tools.memo import _MAX_ACTIVE
        assert _MAX_ACTIVE == 200

    def test_add_rejects_at_limit(self):
        from butler.tools.memo import tool_memo_add, _memos_dir

        d = _memos_dir()
        d.mkdir(parents=True, exist_ok=True)
        for i in range(200):
            (d / f"fake{i:04d}.json").write_text(
                json.dumps({"id": f"fake{i:04d}", "content": f"M{i}", "status": "active"}),
                encoding="utf-8",
            )

        result = json.loads(tool_memo_add(content="Overflow"))
        assert result["ok"] is False
        assert "200" in result["error"] or "limit" in result["error"].lower()

    def test_content_truncated_at_2000(self):
        from butler.tools.memo import tool_memo_add, _memos_dir

        result = json.loads(tool_memo_add(content="x" * 5000))
        assert result["ok"] is True

        d = _memos_dir()
        files = list(d.glob("*.json"))
        data = json.loads(files[0].read_text(encoding="utf-8"))
        assert len(data["content"]) <= 2000

    def test_priority_enum_closed(self):
        from butler.tools.memo import _VALID_PRIORITIES
        assert _VALID_PRIORITIES == frozenset({"low", "normal", "high", "urgent"})

    def test_invalid_priority_defaults(self):
        from butler.tools.memo import _normalize_priority
        assert _normalize_priority("critical") == "normal"

    def test_category_enum_closed(self):
        from butler.tools.memo import _VALID_CATEGORIES
        assert "general" in _VALID_CATEGORIES
        assert "xxx" not in _VALID_CATEGORIES

    def test_archived_memos_dont_count(self):
        """Archived memos should not count toward the active limit."""
        from butler.tools.memo import tool_memo_add, _memos_dir

        d = _memos_dir()
        d.mkdir(parents=True, exist_ok=True)
        for i in range(200):
            (d / f"arch{i:04d}.json").write_text(
                json.dumps({"id": f"arch{i:04d}", "content": f"A{i}", "status": "archived"}),
                encoding="utf-8",
            )
        result = json.loads(tool_memo_add(content="StillFits"))
        assert result["ok"] is True


# ── Expense bounded ───────────────────────────────────────────

class TestExpenseBounded:
    def test_max_records_constant(self):
        from butler.tools.expense import _MAX_RECORDS
        assert _MAX_RECORDS == 5000

    def test_add_rejects_at_limit(self):
        from butler.tools.expense import tool_expense_add, _expenses_dir
        from butler.tools._file_cache import clear_cache

        d = _expenses_dir()
        d.mkdir(parents=True, exist_ok=True)
        for i in range(5000):
            (d / f"fake{i:05d}.json").write_text(
                json.dumps({"id": f"fake{i:05d}", "amount": 10.0}),
                encoding="utf-8",
            )
        clear_cache()

        result = json.loads(tool_expense_add(amount=1.0, description="Over"))
        assert result["ok"] is False
        assert "5000" in result["error"] or "limit" in result["error"].lower()

    def test_description_truncated_at_200(self):
        from butler.tools.expense import tool_expense_add, _expenses_dir

        result = json.loads(tool_expense_add(amount=10.0, description="d" * 500))
        assert result["ok"] is True

        d = _expenses_dir()
        files = list(d.glob("*.json"))
        data = json.loads(files[0].read_text(encoding="utf-8"))
        assert len(data["description"]) <= 200

    def test_amount_must_be_positive(self):
        from butler.tools.expense import tool_expense_add
        r = json.loads(tool_expense_add(amount=-5.0))
        assert r["ok"] is False
        assert "positive" in r["error"].lower()

    def test_direction_enum_closed(self):
        from butler.tools.expense import _VALID_DIRECTIONS
        assert _VALID_DIRECTIONS == frozenset({"income", "expense"})

    def test_category_enum_closed(self):
        from butler.tools.expense import _VALID_CATEGORIES
        assert len(_VALID_CATEGORIES) == 11
        assert "food" in _VALID_CATEGORIES


# ── Habits bounded ────────────────────────────────────────────

class TestHabitsBounded:
    def test_max_habits_constant(self):
        from butler.tools.habits import _MAX_HABITS
        assert _MAX_HABITS == 30

    def test_create_rejects_at_limit(self):
        from butler.tools.habits import tool_habit_create, _habits_dir
        from butler.tools._file_cache import clear_cache

        d = _habits_dir()
        d.mkdir(parents=True, exist_ok=True)
        for i in range(30):
            (d / f"hab{i:03d}.json").write_text(
                json.dumps({"id": f"hab{i:03d}", "name": f"H{i}", "active": True}),
                encoding="utf-8",
            )
        clear_cache()

        result = json.loads(tool_habit_create(name="Overflow"))
        assert result["ok"] is False
        assert "30" in result["error"] or "limit" in result["error"].lower()

    def test_frequency_enum_closed(self):
        from butler.tools.habits import _VALID_FREQUENCIES
        assert _VALID_FREQUENCIES == frozenset({"daily", "weekly"})

    def test_archived_habits_dont_count(self):
        from butler.tools.habits import tool_habit_create, _habits_dir
        from butler.tools._file_cache import clear_cache

        d = _habits_dir()
        d.mkdir(parents=True, exist_ok=True)
        for i in range(30):
            (d / f"arc{i:03d}.json").write_text(
                json.dumps({"id": f"arc{i:03d}", "name": f"AH{i}", "active": False}),
                encoding="utf-8",
            )
        clear_cache()

        result = json.loads(tool_habit_create(name="StillFits"))
        assert result["ok"] is True


# ── Checkin idempotency (P-PIM2) ──────────────────────────────

class TestCheckinIdempotency:
    def test_same_day_accumulates_count(self):
        from butler.tools.habits import tool_habit_create, tool_habit_checkin
        from butler.tools._file_cache import clear_cache

        r1 = json.loads(tool_habit_create(name="Water"))
        assert r1["ok"] is True
        hid = r1["habit_id"]
        clear_cache()

        r2 = json.loads(tool_habit_checkin(habit_id=hid, count=1, date="2026-06-01"))
        assert r2["ok"] is True
        assert r2["count"] == 1
        clear_cache()

        r3 = json.loads(tool_habit_checkin(habit_id=hid, count=2, date="2026-06-01"))
        assert r3["ok"] is True
        assert r3["count"] == 3

    def test_same_day_appends_notes(self):
        from butler.tools.habits import tool_habit_create, tool_habit_checkin, _get_checkin
        from butler.tools._file_cache import clear_cache

        r1 = json.loads(tool_habit_create(name="Exercise"))
        hid = r1["habit_id"]
        clear_cache()

        tool_habit_checkin(habit_id=hid, note="morning run", date="2026-06-02")
        clear_cache()
        tool_habit_checkin(habit_id=hid, note="evening walk", date="2026-06-02")
        clear_cache()

        ci = _get_checkin(hid, "2026-06-02")
        assert ci is not None
        assert "morning run" in ci["note"]
        assert "evening walk" in ci["note"]

    def test_different_days_are_separate(self):
        from butler.tools.habits import tool_habit_create, tool_habit_checkin, _get_checkin
        from butler.tools._file_cache import clear_cache

        r1 = json.loads(tool_habit_create(name="Reading"))
        hid = r1["habit_id"]
        clear_cache()

        tool_habit_checkin(habit_id=hid, count=1, date="2026-06-03")
        clear_cache()
        tool_habit_checkin(habit_id=hid, count=1, date="2026-06-04")
        clear_cache()

        ci3 = _get_checkin(hid, "2026-06-03")
        ci4 = _get_checkin(hid, "2026-06-04")
        assert ci3 is not None and ci4 is not None
        assert ci3["count"] == 1
        assert ci4["count"] == 1

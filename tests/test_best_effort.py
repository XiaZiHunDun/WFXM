"""Tests for safe_best_effort helper (P0-A)."""

from __future__ import annotations

from butler.core.best_effort import recent_best_effort_skips, safe_best_effort


def test_safe_best_effort_returns_value():
    assert safe_best_effort(lambda: 42, label="test.ok") == 42


def test_safe_best_effort_returns_default_on_error():
    def _boom() -> int:
        raise RuntimeError("nope")

    assert safe_best_effort(_boom, label="test.fail", default=0) == 0


def test_safe_best_effort_records_recent_skip():
    def _boom() -> None:
        raise ValueError("recent")

    safe_best_effort(_boom, label="test.recent", default=None)
    recent = recent_best_effort_skips(3)
    assert any("test.recent" in row[1] for row in recent)

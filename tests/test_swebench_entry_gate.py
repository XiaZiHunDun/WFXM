"""Tests for butler.ops.swebench_entry_gate."""

from __future__ import annotations

import json

from butler.ops.swebench_entry_gate import (
    evaluate_swe_full_entry_gate,
    record_swe_weekly_snapshot,
)


def test_record_swe_weekly_snapshot_idempotent(tmp_path, monkeypatch):
    audit = tmp_path / "audit"
    audit.mkdir()
    path = audit / "swe_weekly_snapshots.jsonl"
    monkeypatch.setattr(
        "butler.ops.swebench_entry_gate.snapshots_path",
        lambda: path,
    )
    record_swe_weekly_snapshot(week=10, passed=2, total=3, mode="live", instance_ids=["a"])
    record_swe_weekly_snapshot(week=10, passed=3, total=3, mode="live", instance_ids=["a", "b", "c"])
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(rows) == 1
    assert rows[0]["passed"] == 3
    assert rows[0]["pass_rate"] == 1.0


def test_evaluate_gate_blocks_without_snapshots(tmp_path, monkeypatch):
    audit = tmp_path / "audit"
    audit.mkdir()
    path = audit / "swe_weekly_snapshots.jsonl"
    monkeypatch.setattr(
        "butler.ops.swebench_entry_gate.snapshots_path",
        lambda: path,
    )
    gate = evaluate_swe_full_entry_gate()
    assert gate["allowed"] is False
    assert gate["reason"] == "no_snapshots"


def test_evaluate_gate_two_consecutive_weeks(tmp_path, monkeypatch):
    audit = tmp_path / "audit"
    audit.mkdir()
    path = audit / "swe_weekly_snapshots.jsonl"
    monkeypatch.setattr(
        "butler.ops.swebench_entry_gate.snapshots_path",
        lambda: path,
    )
    record_swe_weekly_snapshot(week=8, passed=3, total=3, mode="live")
    gate = evaluate_swe_full_entry_gate()
    assert gate["allowed"] is False
    assert gate["reason"] == "only_1_qualifying_week"
    record_swe_weekly_snapshot(week=9, passed=3, total=3, mode="live")
    gate = evaluate_swe_full_entry_gate()
    assert gate["allowed"] is True
    assert gate["qualifying_weeks"] == [9, 8]


def test_evaluate_gate_breaks_on_failed_week(tmp_path, monkeypatch):
    audit = tmp_path / "audit"
    audit.mkdir()
    path = audit / "swe_weekly_snapshots.jsonl"
    monkeypatch.setattr(
        "butler.ops.swebench_entry_gate.snapshots_path",
        lambda: path,
    )
    record_swe_weekly_snapshot(week=7, passed=3, total=3, mode="live")
    record_swe_weekly_snapshot(week=8, passed=2, total=3, mode="live")
    record_swe_weekly_snapshot(week=9, passed=3, total=3, mode="live")
    gate = evaluate_swe_full_entry_gate()
    assert gate["allowed"] is False
    assert gate["qualifying_weeks"] == [9]

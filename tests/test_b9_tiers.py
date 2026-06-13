"""Tests for B9 LIVE tier split."""

from __future__ import annotations

from butler.dev_engine.b9_live_fixed_tasks import B9_LIVE_FIXED_TASKS
from butler.dev_engine.b9_tiers import (
    B9_TIER2_TASK_IDS,
    b9_task_tier,
    evaluate_tier2_probe_gate,
    filter_tier_tasks,
    summarize_tier_results,
)


def test_tier2_task_ids_are_tier2():
    for task_id in B9_TIER2_TASK_IDS:
        assert b9_task_tier(task_id) == 2


def test_tier1_tasks_exclude_tier2():
    tier1 = filter_tier_tasks(B9_LIVE_FIXED_TASKS, tier=1)
    tier2 = filter_tier_tasks(B9_LIVE_FIXED_TASKS, tier=2)
    assert len(tier1) + len(tier2) == len(B9_LIVE_FIXED_TASKS)
    assert not {t.task_id for t in tier1} & B9_TIER2_TASK_IDS
    assert {t.task_id for t in tier2} == B9_TIER2_TASK_IDS


def test_summarize_tier_results_excludes_stuck():
    rows = [
        {"task_id": "B9L_stuck_unsolvable", "passed": True},
        {"task_id": "B9L_two_file_patch", "passed": True},
        {"task_id": "B9L_multi_file_import", "passed": False},
    ]
    tiers = summarize_tier_results(rows)
    assert tiers["tier1"]["passed"] == 1
    assert tiers["tier1"]["total"] == 1
    assert tiers["tier2"]["passed"] == 0
    assert tiers["tier2"]["total"] == 1


def test_tier2_probe_gate_default(monkeypatch):
    monkeypatch.delenv("BUTLER_B9_TIER2_GATE_ENABLED", raising=False)
    monkeypatch.delenv("BUTLER_B9_TIER2_GATE_MIN_PASSED", raising=False)
    gate = evaluate_tier2_probe_gate(passed=2, total=3)
    assert gate["enabled"] is True
    assert gate["min_passed"] == 2
    assert gate["ok"] is True
    gate_fail = evaluate_tier2_probe_gate(passed=1, total=3)
    assert gate_fail["ok"] is False


def test_tier2_probe_gate_disabled(monkeypatch):
    monkeypatch.setenv("BUTLER_B9_TIER2_GATE_ENABLED", "0")
    gate = evaluate_tier2_probe_gate(passed=0, total=3)
    assert gate["ok"] is True


def test_tier2_probe_gate_default(monkeypatch):
    monkeypatch.delenv("BUTLER_B9_TIER2_GATE_ENABLED", raising=False)
    monkeypatch.delenv("BUTLER_B9_TIER2_GATE_MIN_PASSED", raising=False)
    gate = evaluate_tier2_probe_gate(passed=2, total=3)
    assert gate["enabled"] is True
    assert gate["min_passed"] == 2
    assert gate["ok"] is True
    gate_fail = evaluate_tier2_probe_gate(passed=1, total=3)
    assert gate_fail["ok"] is False


def test_tier2_probe_gate_disabled(monkeypatch):
    monkeypatch.setenv("BUTLER_B9_TIER2_GATE_ENABLED", "0")
    gate = evaluate_tier2_probe_gate(passed=0, total=3)
    assert gate["ok"] is True

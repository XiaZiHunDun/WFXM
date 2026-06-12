"""Tests for B9 harness friction audit."""

from __future__ import annotations

import json

from butler.ops.b9_harness_audit import (
    compare_harness_friction_delta,
    format_harness_friction_report,
    record_harness_friction_snapshot,
    summarize_harness_friction,
)


def test_summarize_harness_friction_empty(monkeypatch, tmp_path):
    audit = tmp_path / "audit"
    audit.mkdir()
    monkeypatch.setattr(
        "butler.ops.b9_harness_audit._audit_paths",
        lambda: (audit / "delegate_failures.jsonl", audit / "b9_lessons.jsonl"),
    )
    summary = summarize_harness_friction()
    assert summary["delegate_failures_b9_rows"] == 0
    assert summary["read_state_total"] == 0


def test_summarize_harness_friction_read_state(monkeypatch, tmp_path):
    audit = tmp_path / "audit"
    audit.mkdir()
    failures = audit / "delegate_failures.jsonl"
    failures.write_text(
        json.dumps({
            "task_preview": "b9-benchmark B9L_test_driven_add",
            "issues": ["READ_STATE_REQUIRED: must read_file first"],
            "failure_reason": "code:READ_STATE_REQUIRED",
        })
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "butler.ops.b9_harness_audit._audit_paths",
        lambda: (failures, audit / "b9_lessons.jsonl"),
    )
    summary = summarize_harness_friction()
    assert summary["delegate_failures_b9_rows"] == 1
    assert summary["read_state_total"] >= 1
    assert "READ_STATE_REQUIRED" in summary["read_state_by_code"]
    report = format_harness_friction_report(summary)
    assert "harness friction" in report


def test_harness_friction_delta(monkeypatch, tmp_path):
    audit = tmp_path / "audit"
    audit.mkdir()
    snap = audit / "b9_harness_snapshots.jsonl"
    snap.write_text(
        json.dumps({"read_state_total": 100, "tool_error_total": 50, "recorded_at": 1})
        + "\n"
        + json.dumps({"read_state_total": 80, "tool_error_total": 45, "recorded_at": 2})
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "butler.ops.b9_harness_audit.harness_snapshots_path",
        lambda: snap,
    )
    delta = compare_harness_friction_delta()
    assert delta["read_state_total_delta"] == -20
    assert delta["tool_error_total_delta"] == -5

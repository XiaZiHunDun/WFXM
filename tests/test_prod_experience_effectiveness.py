"""Tests for prod experience effectiveness metrics (P0)."""

from __future__ import annotations

import json
import time

from butler.ops.prod_experience_effectiveness import (
    format_prod_experience_effectiveness,
    record_dev_delegate_outcome,
    summarize_prod_experience_effectiveness,
    summarize_prod_repeat_failures,
)


def test_should_filter_b9_benchmark_outcome():
    out = record_dev_delegate_outcome(
        role="dev_agent",
        category="b9-benchmark",
        task_preview="[category:b9-benchmark] fix greet",
        verify_passed=False,
        experience_id="B9_EX_test",
    )
    assert out["recorded"] is False


def test_summarize_pass_rate_by_experience_hit(tmp_path, monkeypatch):
    audit = tmp_path / "audit"
    audit.mkdir()
    path = audit / "delegate_dev_outcomes.jsonl"
    rows = [
        {
            "ts": time.time(),
            "verify_passed": True,
            "experience_hit": True,
            "experience_id": "B9_EX_a",
        },
        {
            "ts": time.time(),
            "verify_passed": False,
            "experience_hit": True,
            "experience_id": "B9_EX_a",
        },
        {
            "ts": time.time(),
            "verify_passed": False,
            "experience_hit": False,
            "experience_id": "",
        },
        {
            "ts": time.time(),
            "verify_passed": False,
            "experience_hit": False,
            "experience_id": "",
        },
    ]
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    monkeypatch.setattr(
        "butler.ops.prod_experience_effectiveness.outcomes_path",
        lambda: path,
    )
    summary = summarize_prod_experience_effectiveness()
    assert summary["experience_hit_total"] == 2
    assert summary["experience_miss_total"] == 2
    assert summary["prod_verify_pass_rate_hit"] == 0.5
    assert summary["prod_verify_pass_rate_miss"] == 0.0
    assert summary["prod_verify_pass_delta_hit_minus_miss"] == 0.5
    text = format_prod_experience_effectiveness(summary)
    assert "prod_verify_pass_rate_hit=0.5" in text


def test_record_production_outcome_with_project(tmp_path, monkeypatch):
    audit = tmp_path / "audit"
    audit.mkdir()
    path = audit / "delegate_dev_outcomes.jsonl"
    monkeypatch.setattr(
        "butler.ops.prod_experience_effectiveness.outcomes_path",
        lambda: path,
    )
    out = record_dev_delegate_outcome(
        role="dev",
        project="灵文1号",
        task_preview="Fix demo/hello.py add()",
        verify_passed=True,
        success=True,
        experience_id="PROD_FAIL_abc",
        experience_mode="experience_guided",
    )
    assert out["recorded"] is True
    row = json.loads(path.read_text(encoding="utf-8").strip())
    assert row["experience_hit"] is True
    assert row["project"] == "灵文1号"


def test_summarize_prod_repeat_failures(tmp_path, monkeypatch):
    audit = tmp_path / "audit"
    audit.mkdir()
    path = audit / "delegate_failures.jsonl"
    now = time.time()
    rows = [
        {
            "ts": now,
            "role": "dev",
            "project": "灵文1号",
            "capture_source": "delegate_pipeline",
            "failure_reason": "verify_fail",
            "task_preview": "fix a",
        },
        {
            "ts": now - 3600,
            "role": "dev",
            "project": "灵文1号",
            "capture_source": "delegate_pipeline",
            "failure_reason": "verify_fail",
            "task_preview": "fix b",
        },
        {
            "ts": now,
            "role": "dev",
            "project": "Other",
            "capture_source": "delegate_pipeline",
            "failure_reason": "patch_wrong",
            "task_preview": "fix c",
        },
    ]
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    monkeypatch.setattr("butler.ops.b9_prod_weekly._audit_path", lambda: path)
    repeat = summarize_prod_repeat_failures(window_days=7.0, clean=True)
    assert repeat["repeat_bucket_count"] == 1
    assert repeat["repeat_pairs"][0]["project"] == "灵文1号"
    assert repeat["repeat_pairs"][0]["classification"] == "verify_fail"
    assert repeat["repeat_pairs"][0]["count"] == 2

"""Production delegate weekly metrics and promotion."""

from __future__ import annotations

import json

from butler.ops.b9_prod_weekly import (
    compare_production_delegate_delta,
    is_production_delegate_row,
    promote_latest_production_failure,
    record_production_delegate_snapshot,
    run_promoted_prod_live_probe,
    summarize_production_delegate_quality,
)
from butler.ops.b9_prod_promoted_registry import PROMOTED_TASK_IDS


def test_is_production_delegate_row_filters_b9():
    assert is_production_delegate_row(
        {"role": "dev", "task_preview": "Fix greet.py", "failure_reason": "verify_fail"}
    )
    assert not is_production_delegate_row(
        {"role": "dev", "category": "b9-benchmark", "failure_reason": "wrong_patch"}
    )
    assert not is_production_delegate_row(
        {
            "role": "dev",
            "task_preview": "[category:swe-benchmark] SWE instance rules",
            "failure_reason": "verify_failed",
        }
    )


def test_summarize_production_delegate_quality(tmp_path, monkeypatch):
    audit = tmp_path / "audit"
    audit.mkdir()
    path = audit / "delegate_failures.jsonl"
    rows = [
        {"role": "dev", "failure_reason": "verify_fail", "task_preview": "fix a"},
        {"role": "dev", "failure_reason": "patch_wrong", "task_preview": "fix b"},
        {"role": "dev", "category": "b9-benchmark", "failure_reason": "wrong_patch"},
    ]
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    monkeypatch.setattr("butler.ops.b9_prod_weekly._audit_path", lambda: path)
    summary = summarize_production_delegate_quality()
    assert summary["production_failures_total"] == 2
    assert summary["by_failure_reason"]["verify_fail"] == 1
    assert summary["rates"]["patch_wrong"] == 0.5


def test_production_snapshot_delta(tmp_path, monkeypatch):
    audit = tmp_path / "audit"
    audit.mkdir()
    monkeypatch.setattr("butler.ops.b9_prod_weekly._audit_path", lambda: audit / "delegate_failures.jsonl")
    snap_path = audit / "prod_delegate_snapshots.jsonl"
    monkeypatch.setattr("butler.ops.b9_prod_weekly.production_snapshots_path", lambda: snap_path)
    (audit / "delegate_failures.jsonl").write_text(
        json.dumps({"role": "dev", "failure_reason": "verify_fail", "task_preview": "x"}) + "\n",
        encoding="utf-8",
    )
    record_production_delegate_snapshot()
    (audit / "delegate_failures.jsonl").write_text(
        "\n".join(
            json.dumps({"role": "dev", "failure_reason": "verify_fail", "task_preview": f"x{i}"})
            for i in range(3)
        )
        + "\n",
        encoding="utf-8",
    )
    snap = record_production_delegate_snapshot()
    delta = snap.get("delta") or compare_production_delegate_delta()
    assert delta.get("snapshots", 0) >= 2


def test_promote_latest_production_failure(tmp_path, monkeypatch):
    audit = tmp_path / "audit"
    audit.mkdir()
    path = audit / "delegate_failures.jsonl"
    path.write_text(
        json.dumps(
            {
                "role": "dev",
                "failure_reason": "verify_fail",
                "task_preview": "Fix greet.py return hello",
                "task_id": "fix-greet",
                "trace_id": "t-1",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("butler.config.get_butler_home", lambda: tmp_path)
    monkeypatch.setattr("butler.ops.b9_prod_weekly._audit_path", lambda: path)
    out = promote_latest_production_failure()
    assert out["promoted"] is True
    queue = tmp_path / "audit" / "b9_promotion_queue.jsonl"
    assert queue.is_file()
    out2 = promote_latest_production_failure()
    assert out2["promoted"] is False
    assert out2["reason"] == "already_queued"


def test_run_promoted_prod_oracle_probe():
    probe = run_promoted_prod_live_probe(mode="oracle")
    assert probe["total"] == len(PROMOTED_TASK_IDS)
    assert probe["passed"] == probe["total"]


def test_promote_resolves_implemented_task(tmp_path, monkeypatch):
    audit = tmp_path / "audit"
    audit.mkdir()
    path = audit / "delegate_failures.jsonl"
    path.write_text(
        json.dumps(
            {
                "role": "dev",
                "failure_reason": "verify_fail",
                "task_preview": "Fix greet.py so greet() returns 'hello' instead of 'hi'.",
                "issues": ["pytest failed"],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("butler.config.get_butler_home", lambda: tmp_path)
    monkeypatch.setattr("butler.ops.b9_prod_weekly._audit_path", lambda: path)
    out = promote_latest_production_failure()
    assert out["reason"] == "already_implemented"
    assert out["resolved_task_id"] == "B9L_prod_demo_fix_greet_return"

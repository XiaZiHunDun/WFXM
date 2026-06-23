"""Tests for G1-04 production eval_feedback evidence."""

from __future__ import annotations

import json

import pytest

from butler.ops.boundary_observability import classify_feedback_evidence
from butler.ops.g1_04_prod_evidence import record_g1_04_production_evidence


@pytest.mark.unit
def test_classify_prod_delegate_triggers():
    assert classify_feedback_evidence({"trigger": "prod_delegate_failure"}) == "production"
    assert classify_feedback_evidence({"trigger": "prod_delegate_verify_pass"}) == "production"
    assert classify_feedback_evidence({"trigger": "b9_live_low_pass"}) == "b9_eval"


@pytest.mark.unit
def test_record_production_evidence(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    monkeypatch.setenv("BUTLER_EVAL_PROD_EVIDENCE", "1")
    from butler.config import reload_butler_settings

    reload_butler_settings()

    out = record_g1_04_production_evidence(
        role="dev",
        project="灵文1号",
        success=True,
        verify_passed=True,
        task_preview="patch docs/flywheel.md read_file confirm",
        capture_source="delegate_pipeline",
    )
    assert out.get("recorded") is True
    assert out.get("trigger") == "prod_delegate_verify_pass"

    audit = tmp_path / "audit" / "eval_feedback.jsonl"
    rows = [json.loads(line) for line in audit.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert rows[-1]["trigger"] == "prod_delegate_verify_pass"

    dup = record_g1_04_production_evidence(
        role="dev",
        project="灵文1号",
        success=True,
        verify_passed=True,
        task_preview="patch docs/flywheel.md read_file confirm",
        capture_source="delegate_pipeline",
    )
    assert dup.get("recorded") is False
    assert dup.get("reason") == "deduped"


@pytest.mark.unit
def test_record_skips_b9_noise(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    monkeypatch.setenv("BUTLER_EVAL_PROD_EVIDENCE", "1")
    out = record_g1_04_production_evidence(
        role="dev",
        project="灵文1号",
        success=False,
        task_preview="[category:b9-benchmark]",
        capture_source="delegate_pipeline",
        category="b9-benchmark",
    )
    assert out.get("recorded") is False

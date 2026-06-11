"""Tests for delegate failure → B9 candidate export."""

from __future__ import annotations

import json
from pathlib import Path

from butler.ops.delegate_failure_b9_import import (
    export_b9_candidates,
    failure_to_b9_candidate,
)


def test_failure_to_b9_candidate_shape():
    cand = failure_to_b9_candidate({
        "task_preview": "Fix hello.py return value",
        "failure_reason": "verify_fail",
        "task_id": "job-123",
        "trace_id": "tr-1",
    })
    assert cand["suggested_task_id"].startswith("B9L_prod_")
    assert cand["failure_reason"] == "verify_fail"
    assert "promotion_checklist" in cand
    assert len(cand["promotion_checklist"]) >= 3


def test_export_b9_candidates_writes_file(tmp_path, monkeypatch):
    audit = tmp_path / "delegate_failures.jsonl"
    audit.write_text(
        json.dumps({
            "task_preview": "create marker file",
            "failure_reason": "patch_wrong",
            "task_id": "t1",
        }) + "\n",
        encoding="utf-8",
    )

    def _fake_summary(*, limit: int = 200):
        rec = json.loads(audit.read_text(encoding="utf-8").strip())
        return {
            "total": 1,
            "by_reason": {"patch_wrong": 1},
            "recent": [rec],
            "audit_path": str(audit),
        }

    monkeypatch.setattr(
        "butler.ops.delegate_failure_b9_import.failure_audit_summary",
        _fake_summary,
    )
    out = tmp_path / "b9_candidates.json"
    payload = export_b9_candidates(limit=5, out_path=out)
    assert payload["total"] == 1
    assert out.is_file()

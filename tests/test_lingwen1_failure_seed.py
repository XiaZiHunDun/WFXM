"""LingWen1 production failure audit seed."""

from __future__ import annotations

import json

from butler.ops.lingwen1_failure_seed import (
    LINGWEN1_AUDIT_RECORD,
    lingwen1_audit_present,
    seed_lingwen1_failure_audit,
)


def test_seed_lingwen1_failure_audit(tmp_path, monkeypatch):
    monkeypatch.setattr("butler.config.get_butler_home", lambda: tmp_path)
    path = tmp_path / "audit" / "delegate_failures.jsonl"

    assert not lingwen1_audit_present()
    out = seed_lingwen1_failure_audit()
    assert LINGWEN1_AUDIT_RECORD["task_id"] in out["seeded"]
    assert path.is_file()
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert any(r["task_id"] == LINGWEN1_AUDIT_RECORD["task_id"] for r in rows)
    assert rows[0]["project"] == "LingWen1"

    out2 = seed_lingwen1_failure_audit()
    assert out2["seeded"] == []
    assert LINGWEN1_AUDIT_RECORD["task_id"] in out2["skipped"]

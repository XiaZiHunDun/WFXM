"""LingWen1 live capture probe through delegate_failure_capture."""

from __future__ import annotations

import json

from butler.ops.lingwen1_capture_probe import (
    PROBE_TASK_ID,
    lingwen1_live_capture_present,
    run_lingwen1_capture_probe,
)


def test_run_lingwen1_capture_probe(tmp_path, monkeypatch):
    monkeypatch.setattr("butler.config.get_butler_home", lambda: tmp_path)
    monkeypatch.setenv("BUTLER_EVAL_CAPTURE_DELEGATE_FAILURES", "1")
    ws = tmp_path / "lingwen"
    ws.mkdir()
    from types import SimpleNamespace

    proj = SimpleNamespace(name="灵文1号", workspace=ws)

    class _PM:
        def get_project(self, name: str):
            if name == "灵文1号":
                return proj
            return None

    monkeypatch.setattr("butler.project.manager.get_project_manager", lambda: _PM())
    monkeypatch.setattr(
        "butler.ops.b9_lessons.b9_lessons_path",
        lambda: tmp_path / "audit" / "b9_lessons.jsonl",
    )

    out = run_lingwen1_capture_probe()
    assert out["captured"] is True
    path = tmp_path / "audit" / "delegate_failures.jsonl"
    row = json.loads(path.read_text(encoding="utf-8").strip().splitlines()[-1])
    assert row["task_id"] == PROBE_TASK_ID
    assert row["project"] == "灵文1号"
    assert row["capture_source"] == "delegate_pipeline"
    follow = out.get("experience_followup") or {}
    assert follow.get("action") == "upserted"
    assert follow.get("ok") is True

    out2 = run_lingwen1_capture_probe()
    assert out2["reason"] == "already_present"
    assert lingwen1_live_capture_present()

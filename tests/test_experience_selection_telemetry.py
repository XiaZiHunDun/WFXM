"""Experience selection telemetry during dev delegate."""

from __future__ import annotations

import json

from butler.ops.experience_selection_telemetry import (
    record_experience_selection,
    summarize_experience_selections,
)


def test_record_and_summarize(tmp_path, monkeypatch):
    audit = tmp_path / "audit"
    audit.mkdir()
    path = audit / "experience_selections.jsonl"
    monkeypatch.setattr(
        "butler.ops.experience_selection_telemetry.selections_path",
        lambda: path,
    )
    record_experience_selection(
        session_key="dev:1",
        task_preview="fix greet hello",
        experience_id="B9_EX_prod_demo_fix_greet_return",
        experience_mode="experience_guided",
        keywords=["fix", "greet"],
    )
    record_experience_selection(
        session_key="dev:2",
        task_preview="other",
        experience_id="",
    )
    summary = summarize_experience_selections()
    assert summary["total"] == 1
    assert "B9_EX_prod_demo_fix_greet_return" in summary["by_experience"]

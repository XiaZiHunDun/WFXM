"""Experience selection telemetry during dev delegate."""

from __future__ import annotations

import json

from butler.ops.experience_selection_telemetry import (
    apply_selected_experience_lifecycle,
    record_experience_selection,
    summarize_experience_selections,
)
from butler.dev_engine.coding_knowledge import CodingExperience, ExperienceLibrary, TheoremLibrary


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


def test_apply_selected_experience_lifecycle_renew_and_demote(tmp_path, monkeypatch):
    monkeypatch.setattr("butler.config.get_butler_home", lambda: tmp_path)
    path = tmp_path / "coding_experiences.json"
    tlib = TheoremLibrary()
    xlib = ExperienceLibrary(theorem_lib=tlib)
    end = 1e9
    exp = CodingExperience(
        id="B9_EX_test_lifecycle",
        title="lifecycle",
        domain=["b9"],
        theorem_basis={"T01"},
        context="test",
        pattern="patch",
        benchmarks={},
        validity_start=0,
        validity_end=end,
    )
    xlib.add(exp, skip_validation=True)
    xlib.save_to_file(str(path))

    out_ok = apply_selected_experience_lifecycle(
        experience_id="B9_EX_test_lifecycle",
        success=True,
        renew_days=10.0,
    )
    assert out_ok["action"] == "renewed"
    reloaded = ExperienceLibrary.load_from_file(str(path), theorem_lib=tlib)
    assert reloaded.get("B9_EX_test_lifecycle").validity_end > end

    out_fail = apply_selected_experience_lifecycle(
        experience_id="B9_EX_test_lifecycle",
        success=False,
        demote_days=5.0,
    )
    assert out_fail["action"] == "demoted"

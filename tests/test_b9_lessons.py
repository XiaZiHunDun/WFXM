"""Tests for B9 lesson learning loop."""

from __future__ import annotations

import json

from butler.dev_engine.b9_oracle_curriculum import get_episode
from butler.dev_engine.b9_types import B9Result
from butler.dev_engine.llm_delegate_benchmark import B9_TASKS
from butler.ops.b9_lessons import (
    export_curriculum_and_seed_experiences,
    format_b9_lessons_block,
    load_lessons_for_task,
    promote_episode_to_experience,
    record_b9_run_lesson,
)


def test_record_live_failure_lesson(tmp_path, monkeypatch):
    monkeypatch.setattr("butler.ops.b9_lessons.b9_lessons_path", lambda: tmp_path / "lessons.jsonl")
    spec = next(t for t in B9_TASKS if t.task_id == "B9L_two_file_patch")
    result = B9Result(
        task_id=spec.task_id,
        description=spec.description,
        passed=False,
        mode="live",
        tools_used=["read_file"],
        failure_reasons=["assert failed"],
    )
    row = record_b9_run_lesson(result, spec)
    assert row["kind"] == "live_failure"
    assert row["classification"] == "no_edit"
    loaded = load_lessons_for_task(spec.task_id)
    assert len(loaded) == 1


def test_format_b9_lessons_block(tmp_path, monkeypatch):
    monkeypatch.setattr("butler.ops.b9_lessons.b9_lessons_path", lambda: tmp_path / "lessons.jsonl")
    spec = next(t for t in B9_TASKS if t.task_id == "B9L_two_file_patch")
    record_b9_run_lesson(
        B9Result(
            task_id=spec.task_id,
            description=spec.description,
            passed=False,
            mode="live",
            tools_used=["patch", "terminal"],
            failure_reasons=["FAILED test"],
        ),
        spec,
    )
    block = format_b9_lessons_block(spec.task_id)
    assert "<b9-lessons>" in block


def test_promote_episode_to_experience(tmp_path, monkeypatch):
    xlib = tmp_path / "coding_experiences.json"
    monkeypatch.setattr("butler.config.get_butler_home", lambda: tmp_path)
    ep = get_episode("B9L_two_file_patch")
    assert ep is not None
    ok, _ = promote_episode_to_experience(ep, skip_if_exists=False)
    assert ok
    assert xlib.is_file()


def test_export_curriculum_and_seed(tmp_path, monkeypatch):
    monkeypatch.setattr("butler.config.get_butler_home", lambda: tmp_path)
    monkeypatch.setattr(
        "butler.dev_engine.b9_oracle_curriculum.curriculum_audit_path",
        lambda: tmp_path / "audit" / "b9_curriculum.json",
    )
    summary = export_curriculum_and_seed_experiences(task_ids=["B9L_two_file_patch"])
    assert summary["lessons_recorded"] == 1
    assert summary["experiences_added"] == 1
    lessons = tmp_path / "audit" / "b9_lessons.jsonl"
    assert lessons.is_file()

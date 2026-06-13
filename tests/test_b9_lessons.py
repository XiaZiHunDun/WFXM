"""Tests for B9 lesson learning loop."""

from __future__ import annotations

import json

from butler.dev_engine.b9_oracle_curriculum import get_episode
from butler.dev_engine.b9_types import B9Result
from butler.dev_engine.llm_delegate_benchmark import B9_TASKS
from butler.ops.b9_lessons import (
    export_curriculum_and_seed_experiences,
    follow_up_lesson_experience,
    format_b9_lessons_block,
    load_lessons_for_task,
    promote_episode_to_experience,
    record_b9_run_lesson,
    renew_or_promote_live_success,
    upsert_failure_experience,
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
    row = record_b9_run_lesson(result, spec, project="灵文1号")
    assert row["kind"] == "live_failure"
    assert row["project"] == "灵文1号"
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


def test_live_failure_upserts_b9_fail_experience(tmp_path, monkeypatch):
    monkeypatch.setattr("butler.config.get_butler_home", lambda: tmp_path)
    monkeypatch.setattr("butler.ops.b9_lessons.b9_lessons_path", lambda: tmp_path / "lessons.jsonl")
    spec = next(t for t in B9_TASKS if t.task_id == "B9L_two_file_patch")
    result = B9Result(
        task_id=spec.task_id,
        description=spec.description,
        passed=False,
        mode="live",
        tools_used=["patch", "terminal"],
        failure_reasons=["assert failed"],
    )
    row = record_b9_run_lesson(result, spec)
    assert row["experience_followup"]["action"] == "failure_upserted"
    data = json.loads((tmp_path / "coding_experiences.json").read_text(encoding="utf-8"))
    assert any(str(r.get("id", "")).startswith("B9_FAIL_") for r in data)


def test_live_success_renews_experience(tmp_path, monkeypatch):
    monkeypatch.setattr("butler.config.get_butler_home", lambda: tmp_path)
    monkeypatch.setattr("butler.ops.b9_lessons.b9_lessons_path", lambda: tmp_path / "lessons.jsonl")
    ep = get_episode("B9L_two_file_patch")
    assert ep is not None
    promote_episode_to_experience(ep, skip_if_exists=False)
    action, _ = renew_or_promote_live_success(ep)
    assert action == "renewed"
    spec = next(t for t in B9_TASKS if t.task_id == "B9L_two_file_patch")
    row = record_b9_run_lesson(
        B9Result(
            task_id=spec.task_id,
            description=spec.description,
            passed=True,
            mode="live",
        ),
        spec,
    )
    assert row["experience_followup"]["action"] == "renewed"

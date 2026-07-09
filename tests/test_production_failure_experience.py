"""Production failure → L3 experience + b9_lessons with project."""

from __future__ import annotations

import json
from types import SimpleNamespace

from butler.ops.b9_lessons import b9_lessons_path, load_lessons_for_task
from butler.ops.production_failure_experience import (
    build_production_failure_pattern,
    classify_production_failure,
    follow_up_production_capture,
    should_upsert_production_failure_experience,
    upsert_production_failure_experience,
)
from butler.memory.memory_scope import project_coding_experiences_path


def test_classify_tool_wrong():
    cls = classify_production_failure(
        failure_reason="verify_failed",
        issues=["Shell metacharacters are not allowed in terminal commands"],
    )
    assert cls == "tool_wrong"


def test_should_skip_benchmark_category():
    assert not should_upsert_production_failure_experience(
        role="dev",
        success=False,
        project="灵文1号",
        capture_source="delegate_pipeline",
        task_preview="[category:b9-benchmark] fix test",
        task_id="task_x",
    )


def test_should_accept_production_pipeline():
    assert should_upsert_production_failure_experience(
        role="dev",
        success=False,
        project="灵文1号",
        capture_source="delegate_pipeline",
        task_preview="fix constants docstring",
        task_id="task_prod_1",
        dev_engine={"verify_passed": False},
    )


def test_build_pattern_includes_guidance():
    pattern = build_production_failure_pattern(
        project="灵文1号",
        task="fix greet",
        failure_reason="verify_failed",
        classification="verify_fail",
        issues=["AssertionError"],
        inferred_task_id="B9L_prod_demo_fix_greet_return",
    )
    assert "next_time:" in pattern
    assert "run_pytest" in pattern.lower()
    assert "B9L_prod_demo_fix_greet_return" in pattern


def test_upsert_writes_l3_and_lesson(tmp_path, monkeypatch):
    ws = tmp_path / "lingwen"
    ws.mkdir()
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

    out = upsert_production_failure_experience(
        project="灵文1号",
        task="fix greet return hello pytest",
        task_id="task_abc",
        failure_reason="verify_failed",
        issues=["verify failed after patch"],
        dev_engine={"verify_passed": False},
    )
    assert out["ok"] is True
    l3 = project_coding_experiences_path(ws)
    assert l3.is_file()
    records = json.loads(l3.read_text(encoding="utf-8"))
    assert len(records) == 1
    assert records[0]["scope"]["visibility"] == "private"
    assert records[0]["scope"]["project_id"] == "灵文1号"
    assert "next_time:" in records[0]["pattern"]
    assert records[0]["benchmarks"].get("inferred_b9_task")

    lessons = load_lessons_for_task("task_abc")
    assert len(lessons) == 1
    assert lessons[0]["project"] == "灵文1号"
    assert lessons[0]["kind"] == "production_failure"


def test_capture_delegate_failure_triggers_followup(tmp_path, monkeypatch):
    ws = tmp_path / "proj"
    ws.mkdir()
    proj = SimpleNamespace(name="普通试点项目", workspace=ws)

    class _PM:
        def get_project(self, name: str):
            if name == "普通试点项目":
                return proj
            return None

    monkeypatch.setattr("butler.project.manager.get_project_manager", lambda: _PM())
    monkeypatch.setattr("butler.config.get_butler_home", lambda: tmp_path)
    monkeypatch.setattr(
        "butler.ops.b9_lessons.b9_lessons_path",
        lambda: tmp_path / "audit" / "b9_lessons.jsonl",
    )
    monkeypatch.setenv("BUTLER_EVAL_CAPTURE_DELEGATE_FAILURES", "1")

    from butler.ops.delegate_failure_capture import capture_delegate_failure

    summary = capture_delegate_failure(
        role="dev",
        task="implement feature X",
        success=False,
        task_id="task_demo",
        project="普通试点项目",
        capture_source="delegate_pipeline",
        dev_engine={"verify_passed": False},
        failure_reason="verify_failed",
        issues=["pytest failed"],
    )
    assert summary["captured"] is True
    follow = summary.get("experience_followup") or {}
    assert follow.get("action") == "upserted"
    assert follow.get("ok") is True
    assert project_coding_experiences_path(ws).is_file()

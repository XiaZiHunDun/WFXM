"""Tests for B9 LIVE tuning helpers."""

from __future__ import annotations

from butler.dev_engine.b9_live_fixed_tasks import B9_LIVE_FIXED_TASKS
from butler.dev_engine.b9_live_tuning import (
    B9_LIVE_CATEGORY,
    B9_TUNING_PROBE_TASK_IDS,
    build_b9_delegate_args,
    build_b9_task_playbook,
    build_b9_verify_hint,
    filter_tasks_by_ids,
)
from butler.ops.b9_failure_analysis import classify_b9_failure


def test_build_b9_delegate_args_uses_category(tmp_path):
    spec = next(t for t in B9_LIVE_FIXED_TASKS if t.task_id == "B9L_multi_file_import")
    args = build_b9_delegate_args(spec, tmp_path)
    assert args["category"] == B9_LIVE_CATEGORY
    assert "pytest" in args["context"].lower()
    assert args["task"] == spec.delegate_prompt


def test_b9_live_runtime_env_sets_terminal_dev_profile():
    import os
    from butler.dev_engine.b9_live_tuning import b9_live_runtime_env

    with b9_live_runtime_env():
        assert os.environ.get("BUTLER_TERMINAL_PROFILE") == "dev"
        assert os.environ.get("BUTLER_ENABLE_TERMINAL") == "1"


def test_filter_probe_tasks():
    probe = filter_tasks_by_ids(B9_LIVE_FIXED_TASKS, B9_TUNING_PROBE_TASK_IDS)
    assert len(probe) == 3
    assert {t.task_id for t in probe} == set(B9_TUNING_PROBE_TASK_IDS)


def test_classify_no_edit():
    assert classify_b9_failure(
        task_id="B9L_pytest_fix_impl",
        passed=False,
        tools_used=["read_file", "terminal"],
        failure_reasons=["assert 5 == 6"],
    ) == "no_edit"


def test_build_b9_task_playbook_probe():
    assert "helpers" in build_b9_task_playbook("B9L_multi_file_import")
    assert build_b9_task_playbook("B9L_unknown") == ""


def test_build_b9_verify_hint_import():
    hint = build_b9_verify_hint("ModuleNotFoundError: No module named 'helper'")
    assert "import" in hint.lower()


def test_build_b9_delegate_args_includes_playbook(tmp_path):
    spec = next(t for t in B9_LIVE_FIXED_TASKS if t.task_id == "B9L_pytest_fix_impl")
    args = build_b9_delegate_args(spec, tmp_path)
    assert "a * b" in args["context"] or "multiplication" in args["context"]


def test_classify_wrong_patch():
    assert classify_b9_failure(
        task_id="B9L_cross_module_rename",
        passed=False,
        tools_used=["patch", "terminal"],
        failure_reasons=["AssertionError assert False"],
    ) == "wrong_patch"

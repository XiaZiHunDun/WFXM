"""Tests for B9 LIVE tuning helpers."""

from __future__ import annotations

from butler.dev_engine.b9_live_fixed_tasks import B9_LIVE_FIXED_TASKS
from butler.dev_engine.b9_live_tuning import (
    B9_LIVE_CATEGORY,
    B9_TUNING_PROBE_TASK_IDS,
    build_b9_delegate_args,
    filter_tasks_by_ids,
)
from butler.ops.b9_failure_analysis import classify_b9_failure


def test_build_b9_delegate_args_uses_category(tmp_path):
    spec = next(t for t in B9_LIVE_FIXED_TASKS if t.task_id == "B9L_multi_file_import")
    args = build_b9_delegate_args(spec, tmp_path)
    assert args["category"] == B9_LIVE_CATEGORY
    assert "pytest" in args["context"].lower()
    assert args["task"] == spec.delegate_prompt


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


def test_classify_wrong_patch():
    assert classify_b9_failure(
        task_id="B9L_cross_module_rename",
        passed=False,
        tools_used=["patch", "terminal"],
        failure_reasons=["AssertionError assert False"],
    ) == "wrong_patch"

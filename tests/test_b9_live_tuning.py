"""Tests for B9 LIVE tuning helpers."""

from __future__ import annotations

from butler.dev_engine.b9_live_fixed_tasks import B9_LIVE_FIXED_TASKS
from butler.dev_engine.b9_live_tuning import (
    B9_LIVE_CATEGORY,
    B9_TUNING_PROBE_TASK_IDS,
    b9_has_edit_tools,
    build_b9_delegate_args,
    build_b9_no_edit_retry_banner,
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


def test_build_b9_verify_hint_missing_symbol():
    hint = build_b9_verify_hint("ImportError: cannot import name 'ping' from 'service'")
    assert "missing symbol" in hint.lower()


def test_build_b9_verify_hint_did_not_raise():
    hint = build_b9_verify_hint("Failed: DID NOT RAISE <class 'ValueError'>")
    assert "exception" in hint.lower()


def test_build_b9_verify_hint_open_fix():
    hint = build_b9_verify_hint("错误: completed 批次 result 仍为未闭合: status:OPEN_FIX")
    assert "workflow_state" in hint.lower()
    assert "open_fix" in hint.lower() or "status:passed" in hint.lower()


def test_build_b9_delegate_args_includes_playbook(tmp_path):
    spec = next(t for t in B9_LIVE_FIXED_TASKS if t.task_id == "B9L_pytest_fix_impl")
    args = build_b9_delegate_args(spec, tmp_path)
    assert "a * b" in args["context"] or "multiplication" in args["context"]


def test_b9_has_edit_tools():
    assert b9_has_edit_tools(["read_file", "patch"])
    assert not b9_has_edit_tools(["read_file", "list_directory"])


def test_build_b9_no_edit_retry_banner():
    banner = build_b9_no_edit_retry_banner("base context")
    assert "NO-EDIT RETRY" in banner
    assert "patch or write_file" in banner
    assert "base context" in banner


def test_build_b9_no_edit_retry_banner_import_hint():
    banner = build_b9_no_edit_retry_banner(
        "base",
        failure_tail="ImportError: cannot import name 'ping' from 'service'",
    )
    assert "ImportError" in banner
    assert "write_file or patch" in banner


def test_classify_run_pytest_counts_as_verify():
    assert classify_b9_failure(
        task_id="B9L_test_driven_add",
        passed=False,
        tools_used=["write_file", "run_pytest"],
        failure_reasons=["AssertionError"],
    ) == "wrong_patch"
    assert classify_b9_failure(
        task_id="B9L_test_driven_add",
        passed=False,
        tools_used=["write_file"],
        failure_reasons=["assert False"],
    ) == "patch_no_verify"


def test_tier1_playbook_test_driven_add(tmp_path):
    spec = next(t for t in B9_LIVE_FIXED_TASKS if t.task_id == "B9L_test_driven_add")
    args = build_b9_delegate_args(spec, tmp_path)
    assert "ping" in args["context"].lower()
    assert "pong" in args["context"].lower()


def test_delegate_args_include_curriculum(tmp_path):
    spec = next(t for t in B9_LIVE_FIXED_TASKS if t.task_id == "B9L_two_file_patch")
    args = build_b9_delegate_args(spec, tmp_path)
    assert "b9-curriculum" in args["context"]
    assert "THRESHOLD" in args["context"]


def test_classify_wrong_patch():
    assert classify_b9_failure(
        task_id="B9L_cross_module_rename",
        passed=False,
        tools_used=["patch", "terminal"],
        failure_reasons=["AssertionError assert False"],
    ) == "wrong_patch"

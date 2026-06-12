"""Tests for production failure → B9L_prod_* promoted registry."""

from __future__ import annotations

from butler.dev_engine.b9_prod_shaped_tasks import B9_PROD_SHAPED_TASK_IDS
from butler.ops.b9_prod_promoted_registry import (
    PROMOTED_TASK_IDS,
    resolve_production_failure_to_task,
)


def test_resolve_greet_verify_fail():
    rec = {
        "task_preview": "Fix greet.py so greet() returns 'hello' instead of 'hi'.",
        "issues": ["pytest failed: assert 'hi' == 'hello'"],
    }
    assert resolve_production_failure_to_task(rec) == "B9L_prod_demo_fix_greet_return"


def test_resolve_greet_read_state():
    rec = {
        "task_preview": "Fix greet.py so greet() returns 'hello' instead of 'hi'.",
        "issues": ["code: READ_STATE_REQUIRED", "必须先调用 read_file"],
    }
    assert resolve_production_failure_to_task(rec) == "B9L_prod_read_state_greet"


def test_resolve_main_helpers_import():
    rec = {
        "task_preview": "Fix main.py so it imports from helpers.py correctly.",
        "issues": ["code: TOOL_ERROR"],
    }
    assert resolve_production_failure_to_task(rec) == "B9L_prod_main_helpers_import"


def test_resolve_cross_module_rename():
    rec = {
        "task_preview": "Rename method getData to get_data in pkg/client.py and update pkg/__init__.py.",
        "issues": ["READ_STATE_REQUIRED"],
    }
    assert resolve_production_failure_to_task(rec) == "B9L_prod_cross_module_rename"


def test_resolve_lingwen_demo_add():
    rec = {
        "project": "LingWen1",
        "task_preview": "Fix demo/hello.py in LingWen1: add(a, b) must return a + b.",
        "issues": ["pytest failed: assert -1.0 == 8.0"],
    }
    assert resolve_production_failure_to_task(rec) == "B9L_prod_lingwen_demo_add"


def test_resolve_lingwen_workflow_guard():
    rec = {
        "project": "LingWen1",
        "task_preview": "Fix scripts/workflow_guard.py has_open_completed 待修复",
        "issues": ["pytest failed"],
    }
    assert resolve_production_failure_to_task(rec) == "B9L_prod_lingwen_workflow_guard"


def test_promoted_tasks_exist_in_prod_shaped():
    assert len(PROMOTED_TASK_IDS) == 6
    for tid in PROMOTED_TASK_IDS:
        assert tid in B9_PROD_SHAPED_TASK_IDS

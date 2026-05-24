"""Tests for planning mode tool blocks."""

from butler.plan_mode import (
    check_plan_mode_block,
    clear_plan_mode,
    is_plan_mode,
    is_plan_writable_path,
    set_plan_mode,
)


def test_plan_writable_paths():
    assert is_plan_writable_path(".butler/plan/session.md")
    assert is_plan_writable_path("docs/implementation.plan.md")
    assert not is_plan_writable_path("src/main.py")


def test_plan_mode_blocks_mutating_tools():
    clear_plan_mode("sess-plan")
    assert check_plan_mode_block("write_file", {"path": "src/a.py"}, session_key="sess-plan") is None
    set_plan_mode("sess-plan", True)
    assert is_plan_mode("sess-plan")
    msg = check_plan_mode_block("delegate_task", {}, session_key="sess-plan")
    assert msg and "规划模式" in msg
    assert check_plan_mode_block(
        "write_file",
        {"path": ".butler/plan/approach.md"},
        session_key="sess-plan",
    ) is None
    blocked = check_plan_mode_block(
        "write_file",
        {"path": "src/main.py"},
        session_key="sess-plan",
    )
    assert blocked and "规划模式" in blocked
    clear_plan_mode("sess-plan")
    assert not is_plan_mode("sess-plan")

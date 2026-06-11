"""Tests for butler.ops.tool_routing."""

from __future__ import annotations

from butler.ops.tool_routing import (
    detect_routing_antipatterns,
    expects_delegate_task,
    score_runtime_tool_routing,
)


def test_expects_delegate_for_dev_task():
    assert expects_delegate_task("请修复 hello.py 的语法错误") is True
    assert expects_delegate_task("项目列表") is False


def test_delegate_miss_antipattern():
    issues = detect_routing_antipatterns(
        "修复 calc.py 的 bug",
        ["terminal"],
    )
    assert issues
    assert "delegate_miss" in issues[0]


def test_score_good_delegate_routing():
    r = score_runtime_tool_routing(
        "交给开发代理修复测试",
        ["delegate_task"],
    )
    assert r.score >= 0.9


def test_score_bad_terminal_without_delegate():
    r = score_runtime_tool_routing(
        "修复 off-by-one 错误",
        ["terminal"],
    )
    assert r.score <= 0.2
    assert r.details.get("antipatterns")


def test_readonly_query_ok():
    r = score_runtime_tool_routing(
        "查看项目状态",
        ["list_projects"],
    )
    assert r.score >= 0.9

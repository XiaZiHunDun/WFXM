"""PROD-P4-B Owner shortcuts unit tests."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from butler.gateway.owner_delegate_shortcuts import (
    build_cc_handoff_package,
    build_dev_delegate_prompt,
    format_edit_command_usage,
    parse_edit_command_arg,
    try_expand_owner_edit_slash,
)


@pytest.mark.unit
def test_parse_edit_command_arg():
    path, goal = parse_edit_command_arg("docs/foo.md 加一段说明")
    assert path == "docs/foo.md"
    assert goal == "加一段说明"


@pytest.mark.unit
def test_expand_edit_slash_to_delegate_nl():
    out = try_expand_owner_edit_slash(
        "/改 docs/foo.md 加一段说明",
        project_name="演示试点",
    )
    assert out is not None
    assert "委派开发代理" in out
    assert "role=dev" in out
    assert "docs/foo.md" in out


@pytest.mark.unit
def test_expand_edit_empty_arg_returns_none():
    assert try_expand_owner_edit_slash("/改") is None
    assert "用法" in format_edit_command_usage()


@pytest.mark.unit
def test_cc_handoff_package():
    text = build_cc_handoff_package(
        "重构 auth 模块",
        project_name="演示试点",
        workspace="/tmp/DemoPilot",
        session_key="sk1",
    )
    assert "CC 任务包" in text
    assert "重构 auth" in text
    assert "演示试点" in text
    assert "/cc-bridge" in text or "本机" in text


@pytest.mark.unit
def test_build_dev_delegate_prompt():
    p = build_dev_delegate_prompt("src/x.py", "修 bug", project_name="P")
    assert "src/x.py" in p
    assert "修 bug" in p
    assert "P" in p

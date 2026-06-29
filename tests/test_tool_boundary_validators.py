"""AP-1: per-tool parameter boundary validators."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from butler.core.tool_dispatch import dispatch_one_tool
from butler.permissions.tool_boundary_registry import validate_tool_boundary


@pytest.mark.unit
class TestToolBoundaryRegistry:
    def test_delegate_invalid_role(self):
        v = validate_tool_boundary("delegate_task", {"task": "do x", "role": "hacker"})
        assert v is not None
        assert v.code == "BOUNDARY_DELEGATE_ROLE"

    def test_delegate_valid_role(self):
        v = validate_tool_boundary("delegate_task", {"task": "do x", "role": "dev_agent"})
        assert v is None

    def test_delegate_empty_task(self):
        v = validate_tool_boundary("delegate_task", {"task": "  "})
        assert v is not None
        assert v.code == "BOUNDARY_DELEGATE_TASK_EMPTY"

    def test_path_traversal_rejected(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "docs").mkdir()
        v = validate_tool_boundary("read_file", {"path": "../../../etc/passwd"})
        assert v is not None
        assert v.code == "BOUNDARY_PATH_TRAVERSAL"

    def test_terminal_empty_command(self):
        v = validate_tool_boundary("terminal", {"command": ""})
        assert v is not None
        assert v.code == "BOUNDARY_TERMINAL_EMPTY"

    def test_terminal_disallowed_command(self):
        v = validate_tool_boundary("terminal", {"command": "rm -rf /"})
        assert v is not None
        assert v.code == "BOUNDARY_TERMINAL_UNSAFE"

    def test_terminal_allowed_ls(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        v = validate_tool_boundary("terminal", {"command": "ls"})
        assert v is None

    def test_call_tool_requires_server_and_tool(self):
        v = validate_tool_boundary("call_tool", {"server": "", "tool": "x"})
        assert v is not None
        assert v.code == "BOUNDARY_MCP_SERVER"

    def test_call_tool_valid_minimal(self):
        v = validate_tool_boundary(
            "call_tool",
            {"server": "github", "tool": "search", "arguments": {}},
        )
        assert v is None

    def test_unknown_tool_no_boundary(self):
        assert validate_tool_boundary("skills_list", {}) is None

    def test_write_file_content_too_large(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "a.txt").write_text("x", encoding="utf-8")
        v = validate_tool_boundary(
            "write_file",
            {"path": "a.txt", "content": "x" * 3_000_000},
        )
        assert v is not None
        assert v.code == "BOUNDARY_CONTENT_TOO_LARGE"


@pytest.mark.unit
def test_dispatch_one_tool_blocks_boundary_before_dispatch(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    def _boom(_name: str, _args: dict) -> str:
        raise AssertionError("dispatch_tool should not run")

    out = dispatch_one_tool(
        "delegate_task",
        {"task": "x", "role": "evil"},
        dispatch_tool=_boom,
    )
    assert "BOUNDARY_DELEGATE_ROLE" in out or "role" in out.lower()

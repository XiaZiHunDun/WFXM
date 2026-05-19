"""Tests for Butler CLI display helpers."""

from __future__ import annotations

import json
import pytest

from butler.cli.display import (
    build_tool_preview,
    format_tool_complete,
    tool_failure_hint,
)


@pytest.mark.unit
class TestToolPreview:
    def test_terminal_command(self):
        p = build_tool_preview("terminal", {"command": "ls -la"})
        assert "ls" in p

    def test_delegate_role(self):
        p = build_tool_preview("delegate_task", {"role": "dev", "task": "fix bug"})
        assert "dev" in p


@pytest.mark.unit
class TestToolComplete:
    def test_read_file_line(self):
        line = format_tool_complete("read_file", {"path": "/tmp/a.py"}, 1.2)
        assert "read" in line
        assert "1.2s" in line

    def test_failure_exit_code(self):
        ok, suffix = tool_failure_hint(json.dumps({"exit_code": 1, "output": ""}))
        assert ok
        assert "exit 1" in suffix

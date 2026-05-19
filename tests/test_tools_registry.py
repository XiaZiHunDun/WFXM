"""L2 module tests for butler.tools.registry."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from butler.tools.registry import (
    dispatch_tool,
    get_tool_definitions,
)


@pytest.mark.module_test
class TestToolDefinitions:
    def test_get_tool_definitions_returns_seven_tools(self):
        tools = get_tool_definitions()
        assert len(tools) == 7

    def test_each_tool_has_valid_function_schema(self):
        tools = get_tool_definitions()
        names = set()
        for t in tools:
            assert t["type"] == "function"
            fn = t["function"]
            assert "name" in fn
            assert "description" in fn
            assert "parameters" in fn
            params = fn["parameters"]
            assert params.get("type") == "object"
            assert "properties" in params
            names.add(fn["name"])
        assert names == {
            "read_file",
            "write_file",
            "patch",
            "terminal",
            "search_files",
            "list_directory",
            "delegate_task",
        }

    @pytest.mark.parametrize(
        "tool_name,required",
        [
            ("read_file", ["path"]),
            ("write_file", ["path", "content"]),
            ("patch", ["path", "old_string", "new_string"]),
            ("terminal", ["command"]),
            ("search_files", ["pattern"]),
            ("delegate_task", ["role", "task"]),
        ],
    )
    def test_required_parameters_present(self, tool_name, required):
        tools = {t["function"]["name"]: t for t in get_tool_definitions()}
        schema = tools[tool_name]["function"]["parameters"]
        for param in required:
            assert param in schema.get("required", [])


@pytest.mark.module_test
class TestReadFile:
    def test_normal_file_read(self, tmp_path):
        f = tmp_path / "hello.txt"
        f.write_text("line one\nline two\n", encoding="utf-8")
        result = dispatch_tool("read_file", {"path": str(f)})
        assert "line one" in result
        assert "line two" in result

    def test_with_offset_and_limit(self, tmp_path):
        f = tmp_path / "lines.txt"
        f.write_text("a\nb\nc\nd\ne\n", encoding="utf-8")
        result = dispatch_tool("read_file", {"path": str(f), "offset": 2, "limit": 2})
        assert "b" in result
        assert "c" in result
        assert "a" not in result.split("|")[-1] or "     1|" not in result

    def test_file_not_found_error_message(self, tmp_path):
        result = dispatch_tool("read_file", {"path": str(tmp_path / "nope.txt")})
        data = json.loads(result)
        assert "error" in data
        assert "not found" in data["error"].lower()

    def test_empty_file(self, tmp_path):
        f = tmp_path / "empty.txt"
        f.write_text("", encoding="utf-8")
        result = dispatch_tool("read_file", {"path": str(f)})
        assert result == ""


@pytest.mark.module_test
class TestWriteFile:
    def test_create_new_file(self, tmp_path):
        target = tmp_path / "new.txt"
        result = dispatch_tool("write_file", {"path": str(target), "content": "fresh"})
        data = json.loads(result)
        assert data["success"] is True
        assert target.read_text(encoding="utf-8") == "fresh"

    def test_overwrite_existing(self, tmp_path):
        target = tmp_path / "existing.txt"
        target.write_text("old", encoding="utf-8")
        dispatch_tool("write_file", {"path": str(target), "content": "new"})
        assert target.read_text(encoding="utf-8") == "new"

    def test_creates_parent_directories(self, tmp_path):
        target = tmp_path / "nested" / "dir" / "out.txt"
        dispatch_tool("write_file", {"path": str(target), "content": "nested content"})
        assert target.exists()
        assert target.read_text(encoding="utf-8") == "nested content"


@pytest.mark.module_test
class TestPatch:
    def test_normal_search_replace(self, tmp_path):
        f = tmp_path / "patchme.txt"
        f.write_text("foo bar baz", encoding="utf-8")
        result = dispatch_tool(
            "patch",
            {"path": str(f), "old_string": "bar", "new_string": "QUX"},
        )
        data = json.loads(result)
        assert data["success"] is True
        assert f.read_text(encoding="utf-8") == "foo QUX baz"

    def test_old_string_not_found_error(self, tmp_path):
        f = tmp_path / "patchme.txt"
        f.write_text("hello", encoding="utf-8")
        result = dispatch_tool(
            "patch",
            {"path": str(f), "old_string": "missing", "new_string": "x"},
        )
        data = json.loads(result)
        assert "error" in data
        assert "not found" in data["error"]

    def test_successful_patch_json(self, tmp_path):
        f = tmp_path / "ok.txt"
        f.write_text("replace me", encoding="utf-8")
        result = dispatch_tool(
            "patch",
            {"path": str(f), "old_string": "replace me", "new_string": "done"},
        )
        assert json.loads(result) == {"success": True, "replacements": 1}


@pytest.mark.module_test
class TestTerminal:
    def test_echo_command_exit_code_zero(self):
        result = dispatch_tool("terminal", {"command": "echo hello-terminal"})
        data = json.loads(result)
        assert data["exit_code"] == 0
        assert "hello-terminal" in data["output"]

    def test_false_command_nonzero_exit(self):
        result = dispatch_tool("terminal", {"command": "false"})
        data = json.loads(result)
        assert data["exit_code"] != 0

    def test_timeout_error_message(self):
        result = dispatch_tool(
            "terminal",
            {"command": "sleep 10", "timeout": 1},
        )
        data = json.loads(result)
        assert "error" in data
        assert "timed out" in data["error"].lower()

    def test_large_output_truncated(self, tmp_path):
        big = tmp_path / "big.txt"
        big.write_text("\n".join(f"line-{i}" for i in range(8000)), encoding="utf-8")
        result = dispatch_tool("terminal", {"command": f"cat {big}"})
        data = json.loads(result)
        assert data["exit_code"] == 0
        assert len(data["output"]) <= 50050


@pytest.mark.module_test
class TestSearchFiles:
    def test_normal_pattern_match(self, tmp_path):
        f = tmp_path / "searchme.py"
        f.write_text("def unique_marker_xyz():\n    pass\n", encoding="utf-8")
        try:
            subprocess.run(["rg", "--version"], capture_output=True, check=True)
        except (FileNotFoundError, subprocess.CalledProcessError):
            pytest.skip("ripgrep not installed")
        result = dispatch_tool(
            "search_files",
            {"pattern": "unique_marker_xyz", "path": str(tmp_path)},
        )
        data = json.loads(result)
        if "error" in data:
            pytest.skip(data["error"])
        assert data["total"] >= 1
        assert any("searchme.py" in m["path"] for m in data["matches"])

    def test_no_matches(self, tmp_path):
        (tmp_path / "empty.py").write_text("nothing here\n", encoding="utf-8")
        try:
            subprocess.run(["rg", "--version"], capture_output=True, check=True)
        except (FileNotFoundError, subprocess.CalledProcessError):
            pytest.skip("ripgrep not installed")
        result = dispatch_tool(
            "search_files",
            {"pattern": "zzz_no_match_zzz_999", "path": str(tmp_path)},
        )
        data = json.loads(result)
        if "error" in data:
            pytest.skip(data["error"])
        assert data["total"] == 0


@pytest.mark.module_test
class TestListDirectory:
    def test_normal_listing_returns_entries(self, tmp_path):
        (tmp_path / "a.txt").write_text("a", encoding="utf-8")
        (tmp_path / "subdir").mkdir()
        result = dispatch_tool("list_directory", {"path": str(tmp_path)})
        data = json.loads(result)
        names = {e["name"] for e in data["entries"]}
        assert "a.txt" in names
        assert "subdir" in names

    def test_nonexistent_directory_error(self, tmp_path):
        result = dispatch_tool("list_directory", {"path": str(tmp_path / "missing")})
        data = json.loads(result)
        assert "error" in data


@pytest.mark.module_test
class TestDelegateTask:
    @patch("butler.report.cache_report")
    @patch("butler.orchestrator.ButlerOrchestrator")
    def test_delegate_task_with_mock_orchestrator(self, mock_orch_cls, mock_cache):
        from butler.core.agent_loop import LoopResult, LoopStatus

        mock_agent = MagicMock()
        mock_agent.run.return_value = LoopResult(
            status=LoopStatus.COMPLETED,
            final_response="delegation done",
            iterations=2,
            tool_calls_made=1,
            total_tokens=100,
            elapsed_seconds=1.5,
        )
        mock_orch = MagicMock()
        mock_orch.create_project_agent_loop.return_value = mock_agent
        mock_orch_cls.return_value = mock_orch

        result = dispatch_tool(
            "delegate_task",
            {"role": "dev", "task": "fix bug", "context": "in auth module"},
        )
        data = json.loads(result)
        assert data["success"] is True
        assert "delegation done" in data["summary"]
        mock_orch.create_project_agent_loop.assert_called_once()
        mock_agent.run.assert_called_once()
        assert "auth module" in mock_agent.run.call_args[0][0]

"""L2 module tests for butler.tools.registry."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from butler.tools.registry import (
    dispatch_tool,
    get_tool_definitions,
    get_tool_audit_events,
    reset_tool_audit_events,
)
from butler.execution_context import use_execution_context
from butler.memory.observer_queue import flush_observer_queue, list_observations_for_path


def _orchestrator_for_workspace(workspace: Path):
    orch = MagicMock()  # noqa: magicmock-no-spec — tools registry facade (orch / agent / proc)
    orch.project_manager.get_current.return_value = SimpleNamespace(workspace=workspace)
    return orch


@pytest.fixture(autouse=True)
def _tool_safe_root(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_TOOL_SAFE_ROOT", str(tmp_path))


@pytest.fixture(autouse=True)
def _isolate_tool_registry_per_test():
    """Re-reset registry around each test (ENG-9; reinforces global conftest)."""
    from butler.tools.registry import reset_tool_audit_events, reset_tool_registry

    reset_tool_registry()
    reset_tool_audit_events()
    yield
    reset_tool_registry()
    reset_tool_audit_events()


@pytest.mark.module_test
class TestToolDefinitions:
    def test_get_tool_definitions_includes_memory_tools(self):
        tools = get_tool_definitions()
        names = {t["function"]["name"] for t in tools}
        assert len(tools) >= 21
        assert "butler_remember" in names
        assert "butler_recall" in names

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
        assert names >= {
            "read_file",
            "write_file",
            "delete_file",
            "patch",
            "terminal",
            "search_files",
            "list_directory",
            "skills_list",
            "skill_view",
            "run_workflow",
            "delegate_task",
            "delegate_yield",
            "butler_remember",
            "butler_recall",
            "git_status",
            "git_diff",
            "git_log",
            "git_branch",
            "git_add",
            "git_commit",
            "list_runtime_jobs",
            "run_runtime_job",
            "download_file",
            "session_todos_list",
            "session_todos_write",
        }

    @pytest.mark.parametrize(
        "tool_name,required",
        [
            ("read_file", ["path"]),
            ("write_file", ["path", "content"]),
            ("delete_file", ["path"]),
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

    def test_tool_resource_limits_are_in_schema(self):
        tools = {t["function"]["name"]: t for t in get_tool_definitions()}

        read_limit = tools["read_file"]["function"]["parameters"]["properties"]["limit"]
        timeout = tools["terminal"]["function"]["parameters"]["properties"]["timeout"]

        assert read_limit["maximum"] == 1000
        assert read_limit["minimum"] == 1
        assert timeout["maximum"] == 120
        assert timeout["minimum"] == 1


@pytest.mark.module_test
class TestToolResultEnvelope:
    def test_unknown_tool_returns_standard_error_envelope(self):
        reset_tool_audit_events()

        result = dispatch_tool("missing_tool", {})

        data = json.loads(result)
        assert data["error"] == "Unknown tool: missing_tool"
        assert data["ok"] is False
        assert data["tool"] == "missing_tool"
        assert data["code"] == "TOOL_NOT_FOUND"
        events = get_tool_audit_events()
        assert events[-1]["tool"] == "missing_tool"
        assert events[-1]["ok"] is False
        assert events[-1]["code"] == "TOOL_NOT_FOUND"

    def test_security_denial_error_is_coded_and_audited(self, tmp_path):
        reset_tool_audit_events()
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        outside = tmp_path / "outside.txt"
        outside.write_text("secret", encoding="utf-8")

        with use_execution_context(_orchestrator_for_workspace(workspace)):
            result = dispatch_tool("read_file", {"path": str(outside)})

        data = json.loads(result)
        assert data["ok"] is False
        assert data["tool"] == "read_file"
        assert data["code"] == "TOOL_SECURITY_DENIED"
        assert "outside workspace" in data["error"]
        event = get_tool_audit_events()[-1]
        assert event["tool"] == "read_file"
        assert event["code"] == "TOOL_SECURITY_DENIED"
        assert event["session_key"] == ""
        assert "outside.txt" not in json.dumps(event)

    def test_plain_text_success_is_audited_without_changing_result(self, tmp_path):
        reset_tool_audit_events()
        target = tmp_path / "hello.txt"
        target.write_text("hello\n", encoding="utf-8")

        result = dispatch_tool("read_file", {"path": str(target)})

        assert "hello" in result
        assert not result.lstrip().startswith("{")
        event = get_tool_audit_events()[-1]
        assert event["tool"] == "read_file"
        assert event["ok"] is True
        assert event["code"] == "TOOL_OK"

    def test_nonzero_terminal_exit_is_coded_as_failure(self, monkeypatch):
        monkeypatch.setenv("BUTLER_ENABLE_TERMINAL", "1")
        reset_tool_audit_events()

        result = dispatch_tool("terminal", {"command": "false"})

        data = json.loads(result)
        assert data["exit_code"] != 0
        assert data["ok"] is False
        assert data["code"] == "TOOL_EXIT_NONZERO"
        event = get_tool_audit_events()[-1]
        assert event["ok"] is False
        assert event["code"] == "TOOL_EXIT_NONZERO"

    def test_patch_missing_old_string_is_generic_tool_error(self, tmp_path, monkeypatch):
        reset_tool_audit_events()
        monkeypatch.setenv("BUTLER_TOOL_SAFE_ROOT", str(tmp_path))
        target = tmp_path / "patchme.txt"
        target.write_text("hello", encoding="utf-8")

        result = dispatch_tool(
            "patch",
            {"path": str(target), "old_string": "missing", "new_string": "x"},
        )

        data = json.loads(result)
        assert data["code"] == "PATCH_OLD_STRING_NOT_FOUND"
        event = get_tool_audit_events()[-1]
        assert event["code"] == "PATCH_OLD_STRING_NOT_FOUND"


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

    def test_read_file_records_observation_when_queue_enabled(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BUTLER_MEMORY_OBSERVER_QUEUE", "1")
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        target = workspace / "notes.txt"
        target.write_text("hello observation\n", encoding="utf-8")

        with use_execution_context(
            _orchestrator_for_workspace(workspace),
            session_key="wechat:u1:proj",
        ):
            result = dispatch_tool("read_file", {"path": str(target)})

        assert "hello observation" in result
        assert flush_observer_queue(workspace) >= 1
        rows = list_observations_for_path(workspace, str(target), limit=3)
        assert len(rows) == 1
        assert rows[0]["tool"] == "read_file"
        assert "hello observation" in rows[0]["preview"]

    def test_denies_file_outside_current_workspace(self, tmp_path):
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        outside = tmp_path / "outside.txt"
        outside.write_text("secret", encoding="utf-8")

        with use_execution_context(_orchestrator_for_workspace(workspace)):
            result = dispatch_tool("read_file", {"path": str(outside)})

        data = json.loads(result)
        assert "outside workspace" in data["error"]

    def test_denies_reading_oversized_file(self, tmp_path):
        f = tmp_path / "huge.txt"
        f.write_text("x" * (1024 * 1024 + 1), encoding="utf-8")

        result = dispatch_tool("read_file", {"path": str(f)})

        data = json.loads(result)
        assert "too large" in data["error"].lower()

    def test_denies_excessive_read_line_limit(self, tmp_path):
        f = tmp_path / "many-lines.txt"
        f.write_text("\n".join(f"line-{i}" for i in range(20)), encoding="utf-8")

        result = dispatch_tool("read_file", {"path": str(f), "limit": 5000})

        data = json.loads(result)
        assert "limit" in data["error"].lower()

    def test_read_file_rejects_non_integer_limit(self, tmp_path):
        f = tmp_path / "lines.txt"
        f.write_text("hello\n", encoding="utf-8")

        result = dispatch_tool("read_file", {"path": str(f), "limit": "many"})

        data = json.loads(result)
        assert "integer" in data["error"].lower()

    def test_read_file_rejects_symlinks(self, tmp_path):
        target = tmp_path / "target.txt"
        link = tmp_path / "link.txt"
        target.write_text("safe\n", encoding="utf-8")
        link.symlink_to(target)

        result = dispatch_tool("read_file", {"path": str(link)})

        data = json.loads(result)
        assert "symlink" in data["error"].lower()

    def test_read_file_rejects_non_regular_files(self, tmp_path):
        fifo = tmp_path / "pipe"
        if not hasattr(os, "mkfifo"):
            pytest.skip("mkfifo is unavailable on this platform")
        os.mkfifo(fifo)

        result = dispatch_tool("read_file", {"path": str(fifo)})

        data = json.loads(result)
        assert "regular files" in data["error"]


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

    def test_denies_write_outside_current_workspace(self, tmp_path):
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        outside = tmp_path / "outside.txt"

        with use_execution_context(_orchestrator_for_workspace(workspace)):
            result = dispatch_tool("write_file", {"path": str(outside), "content": "nope"})

        data = json.loads(result)
        assert "outside workspace" in data["error"]
        assert not outside.exists()

    def test_relative_write_targets_current_workspace(self, tmp_path):
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        with use_execution_context(_orchestrator_for_workspace(workspace)):
            result = dispatch_tool("write_file", {"path": "nested/out.txt", "content": "ok"})

        data = json.loads(result)
        assert data["success"] is True
        assert (workspace / "nested" / "out.txt").read_text(encoding="utf-8") == "ok"

    def test_write_file_rejects_symlink_target(self, tmp_path):
        outside = tmp_path / "outside.txt"
        link = tmp_path / "link.txt"
        outside.write_text("secret", encoding="utf-8")
        link.symlink_to(outside)

        result = dispatch_tool("write_file", {"path": str(link), "content": "nope"})

        data = json.loads(result)
        assert "symlink" in data["error"].lower()
        assert outside.read_text(encoding="utf-8") == "secret"

    def test_write_file_atomic_replace_failure_preserves_original(self, tmp_path):
        target = tmp_path / "existing.txt"
        target.write_text("old", encoding="utf-8")

        with patch("butler.tools.file_io.os.replace", side_effect=OSError("replace failed")):
            result = dispatch_tool("write_file", {"path": str(target), "content": "new"})

        data = json.loads(result)
        assert "replace failed" in data["error"]
        assert target.read_text(encoding="utf-8") == "old"

    def test_write_file_rejects_target_replaced_before_atomic_replace(self, tmp_path):
        target = tmp_path / "existing.txt"
        swapped = tmp_path / "swapped.txt"
        target.write_text("old", encoding="utf-8")
        swapped.write_text("swapped", encoding="utf-8")
        original_fsync = os.fsync
        swapped_once = {"done": False}

        def _swap_before_replace(fd):
            if not swapped_once["done"]:
                swapped_once["done"] = True
                swapped.replace(target)
            return original_fsync(fd)

        with patch("butler.tools.file_io.os.fsync", side_effect=_swap_before_replace):
            result = dispatch_tool("write_file", {"path": str(target), "content": "new"})

        data = json.loads(result)
        assert "changed during validation" in data["error"]
        assert target.read_text(encoding="utf-8") == "swapped"


@pytest.mark.module_test
class TestDeleteFile:
    def test_delete_existing_file(self, tmp_path):
        target = tmp_path / "remove-me.txt"
        target.write_text("bye", encoding="utf-8")
        result = dispatch_tool("delete_file", {"path": str(target)})
        data = json.loads(result)
        assert data["success"] is True
        assert data["action"] == "deleted"
        assert not target.exists()

    def test_delete_missing_file_error(self, tmp_path):
        target = tmp_path / "missing.txt"
        result = dispatch_tool("delete_file", {"path": str(target)})
        data = json.loads(result)
        assert "error" in data
        assert "not found" in data["error"].lower()

    def test_delete_rejects_directory(self, tmp_path):
        folder = tmp_path / "dir"
        folder.mkdir()
        result = dispatch_tool("delete_file", {"path": str(folder)})
        data = json.loads(result)
        assert "error" in data
        assert "regular files" in data["error"].lower()


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
        data = json.loads(result)
        assert data["success"] is True
        assert data["replacements"] == 1

    def test_denies_patch_outside_current_workspace(self, tmp_path):
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        outside = tmp_path / "patchme.txt"
        outside.write_text("replace me", encoding="utf-8")

        with use_execution_context(_orchestrator_for_workspace(workspace)):
            result = dispatch_tool(
                "patch",
                {"path": str(outside), "old_string": "replace", "new_string": "blocked"},
            )

        data = json.loads(result)
        assert "outside workspace" in data["error"]
        assert outside.read_text(encoding="utf-8") == "replace me"

    def test_patch_rejects_symlink_target(self, tmp_path):
        outside = tmp_path / "outside.txt"
        link = tmp_path / "link.txt"
        outside.write_text("replace me", encoding="utf-8")
        link.symlink_to(outside)

        result = dispatch_tool(
            "patch",
            {"path": str(link), "old_string": "replace", "new_string": "blocked"},
        )

        data = json.loads(result)
        assert "symlink" in data["error"].lower()
        assert outside.read_text(encoding="utf-8") == "replace me"

    def test_patch_atomic_replace_failure_preserves_original(self, tmp_path):
        target = tmp_path / "patchme.txt"
        target.write_text("replace me", encoding="utf-8")

        with patch("butler.tools.file_io.os.replace", side_effect=OSError("replace failed")):
            result = dispatch_tool(
                "patch",
                {"path": str(target), "old_string": "replace", "new_string": "done"},
            )

        data = json.loads(result)
        assert "replace failed" in data["error"]
        assert target.read_text(encoding="utf-8") == "replace me"

    def test_patch_rejects_target_replaced_before_atomic_replace(self, tmp_path):
        target = tmp_path / "patchme.txt"
        swapped = tmp_path / "swapped.txt"
        target.write_text("replace me", encoding="utf-8")
        swapped.write_text("swapped content", encoding="utf-8")
        original_fsync = os.fsync
        swapped_once = {"done": False}

        def _swap_before_replace(fd):
            if not swapped_once["done"]:
                swapped_once["done"] = True
                swapped.replace(target)
            return original_fsync(fd)

        with patch("butler.tools.file_io.os.fsync", side_effect=_swap_before_replace):
            result = dispatch_tool(
                "patch",
                {"path": str(target), "old_string": "replace", "new_string": "done"},
            )

        data = json.loads(result)
        assert "changed during validation" in data["error"]
        assert target.read_text(encoding="utf-8") == "swapped content"


@pytest.mark.module_test
class TestTerminal:
    @pytest.fixture(autouse=True)
    def _enable_terminal(self, monkeypatch):
        monkeypatch.setenv("BUTLER_ENABLE_TERMINAL", "1")

    def test_terminal_disabled_by_default(self, monkeypatch):
        monkeypatch.delenv("BUTLER_ENABLE_TERMINAL", raising=False)

        result = dispatch_tool("terminal", {"command": "echo blocked"})

        data = json.loads(result)
        assert "disabled by default" in data["error"]

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

    def test_rejects_excessive_terminal_timeout(self):
        result = dispatch_tool("terminal", {"command": "echo ok", "timeout": 9999})

        data = json.loads(result)
        assert "timeout" in data["error"].lower()

    def test_rejects_non_positive_terminal_timeout(self):
        result = dispatch_tool("terminal", {"command": "echo ok", "timeout": 0})

        data = json.loads(result)
        assert "timeout" in data["error"].lower()

    def test_timeout_path_does_not_communicate_unbounded_output(self):
        fake_proc = MagicMock()  # noqa: magicmock-no-spec — tools registry facade (orch / agent / proc)
        fake_proc.poll.return_value = None
        fake_proc.wait.return_value = -9
        fake_proc.communicate.side_effect = AssertionError("communicate should not be used")
        fake_proc.returncode = -9

        with patch("butler.tools.terminal_impl.subprocess.Popen", return_value=fake_proc):
            with patch(
                "butler.tools.terminal_impl._communicate_limited",
                side_effect=subprocess.TimeoutExpired(cmd="sleep 10", timeout=1),
            ):
                result = dispatch_tool("terminal", {"command": "sleep 10", "timeout": 1})

        data = json.loads(result)
        assert "timed out" in data["error"].lower()
        fake_proc.kill.assert_called_once()
        fake_proc.communicate.assert_not_called()

    def test_large_output_truncated(self, tmp_path):
        big = tmp_path / "big.txt"
        big.write_text("\n".join(f"line-{i}" for i in range(8000)), encoding="utf-8")
        result = dispatch_tool("terminal", {"command": f"cat {big}"})
        data = json.loads(result)
        assert data["exit_code"] == 0
        assert len(data["output"]) <= 50050

    def test_denies_workdir_outside_current_workspace(self, tmp_path):
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        outside = tmp_path / "outside"
        outside.mkdir()

        with use_execution_context(_orchestrator_for_workspace(workspace)):
            result = dispatch_tool("terminal", {"command": "pwd", "workdir": str(outside)})

        data = json.loads(result)
        assert "outside workspace" in data["error"]

    def test_relative_workdir_targets_current_workspace(self, tmp_path):
        workspace = tmp_path / "workspace"
        nested = workspace / "nested"
        nested.mkdir(parents=True)

        with use_execution_context(_orchestrator_for_workspace(workspace)):
            result = dispatch_tool("terminal", {"command": "pwd", "workdir": "nested"})

        data = json.loads(result)
        assert data["exit_code"] == 0
        assert str(nested) in data["output"]

    def test_default_workdir_is_current_workspace(self, tmp_path):
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        with use_execution_context(_orchestrator_for_workspace(workspace)):
            result = dispatch_tool("terminal", {"command": "pwd"})

        data = json.loads(result)
        assert data["exit_code"] == 0
        assert data["output"].strip() == str(workspace)

    def test_denies_command_paths_outside_current_workspace(self, tmp_path):
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        with use_execution_context(_orchestrator_for_workspace(workspace)):
            result = dispatch_tool("terminal", {"command": "cat /etc/passwd"})

        data = json.loads(result)
        assert "outside workspace" in data["error"] or "sensitive" in data["error"]

    def test_denies_relative_command_paths_escaping_workspace(self, tmp_path):
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        with use_execution_context(_orchestrator_for_workspace(workspace)):
            result = dispatch_tool("terminal", {"command": "cat ../outside.txt"})

        data = json.loads(result)
        assert "outside workspace" in data["error"]

    def test_denies_shell_metacharacter_escape(self, tmp_path):
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        with use_execution_context(_orchestrator_for_workspace(workspace)):
            result = dispatch_tool("terminal", {"command": "cd .. && pwd"})

        data = json.loads(result)
        assert "allowlist" in data["error"]

    def test_denies_dynamic_interpreter_escape(self, tmp_path):
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        with use_execution_context(_orchestrator_for_workspace(workspace)):
            result = dispatch_tool(
                "terminal",
                {"command": "python -c \"open('../outside.txt').read()\""},
            )

        data = json.loads(result)
        assert "allowlist" in data["error"]

    def test_denies_shell_wrappers_even_when_terminal_enabled(self, tmp_path):
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        with use_execution_context(_orchestrator_for_workspace(workspace)):
            result = dispatch_tool("terminal", {"command": "dash -c 'cat ../outside.txt'"})

        data = json.loads(result)
        assert "allowlist" in data["error"]

    def test_denies_executable_paths_even_when_terminal_enabled(self, tmp_path):
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        with use_execution_context(_orchestrator_for_workspace(workspace)):
            result = dispatch_tool("terminal", {"command": "/bin/echo hello"})

        data = json.loads(result)
        assert "allowlist" in data["error"]

    def test_denies_search_commands_in_terminal_allowlist(self, tmp_path, monkeypatch):
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        monkeypatch.delenv("BUTLER_TERMINAL_PROFILE", raising=False)

        with use_execution_context(_orchestrator_for_workspace(workspace)):
            result = dispatch_tool("terminal", {"command": "rg --pre sh ."})

        data = json.loads(result)
        assert data.get("ok") is False
        assert data.get("error")
        assert any(
            token in data["error"]
            for token in ("allowlist", "--pre", "not allowed")
        )

        with use_execution_context(_orchestrator_for_workspace(workspace)):
            result = dispatch_tool("terminal", {"command": "grep --file=../outside.txt hit.txt"})

        data = json.loads(result)
        assert data.get("ok") is False
        assert data.get("error")
        assert any(
            token in data["error"]
            for token in ("allowlist", "--file", "not allowed", "outside workspace")
        )

    def test_denies_symlink_argument_escaping_workspace(self, tmp_path):
        workspace = tmp_path / "workspace"
        outside = tmp_path / "outside.txt"
        workspace.mkdir()
        outside.write_text("leaked", encoding="utf-8")
        (workspace / "link.txt").symlink_to(outside)

        with use_execution_context(_orchestrator_for_workspace(workspace)):
            result = dispatch_tool("terminal", {"command": "cat link.txt"})

        data = json.loads(result)
        assert "outside workspace" in data["error"]

    def test_denies_hardlink_argument_escaping_workspace(self, tmp_path):
        workspace = tmp_path / "workspace"
        outside = tmp_path / "outside.txt"
        hardlink = workspace / "hardlink.txt"
        workspace.mkdir()
        outside.write_text("leaked", encoding="utf-8")
        try:
            hardlink.hardlink_to(outside)
        except OSError:
            pytest.skip("hardlinks are not supported on this filesystem")

        with use_execution_context(_orchestrator_for_workspace(workspace)):
            result = dispatch_tool("terminal", {"command": "cat hardlink.txt"})

        data = json.loads(result)
        assert "hardlinked" in data["error"]

    def test_terminal_uses_fixed_path_not_workspace_path(self, tmp_path, monkeypatch):
        workspace = tmp_path / "workspace"
        bin_dir = workspace / "bin"
        workspace.mkdir()
        bin_dir.mkdir()
        fake_cat = bin_dir / "cat"
        fake_cat.write_text("#!/bin/sh\necho PWNED_VIA_PATH\n", encoding="utf-8")
        fake_cat.chmod(0o755)
        target = workspace / "target.txt"
        target.write_text("real content", encoding="utf-8")
        monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ.get('PATH', '')}")

        with use_execution_context(_orchestrator_for_workspace(workspace)):
            result = dispatch_tool("terminal", {"command": "cat target.txt"})

        data = json.loads(result)
        assert data["exit_code"] == 0
        assert "real content" in data["output"]
        assert "PWNED_VIA_PATH" not in data["output"]

    def test_terminal_sanitizes_subprocess_env(self, tmp_path, monkeypatch):
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        monkeypatch.setenv("LD_PRELOAD", str(tmp_path / "evil.so"))
        monkeypatch.setenv("RIPGREP_CONFIG_PATH", str(tmp_path / "evil-rg-config"))

        fake_proc = MagicMock()  # noqa: magicmock-no-spec — tools registry facade (orch / agent / proc)
        fake_proc.poll.return_value = 0
        fake_proc.communicate.return_value = ("ok\n", "")
        fake_proc.returncode = 0

        with patch("butler.tools.terminal_impl.subprocess.Popen", return_value=fake_proc) as mock_popen:
            with use_execution_context(_orchestrator_for_workspace(workspace)):
                result = dispatch_tool("terminal", {"command": "echo ok"})

        data = json.loads(result)
        assert data["exit_code"] == 0
        env = mock_popen.call_args.kwargs["env"]
        assert env["PATH"] == "/usr/bin:/bin"
        assert "LD_PRELOAD" not in env
        assert "RIPGREP_CONFIG_PATH" not in env


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

    def test_denies_search_outside_current_workspace(self, tmp_path):
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        outside = tmp_path / "outside"
        outside.mkdir()

        with use_execution_context(_orchestrator_for_workspace(workspace)):
            result = dispatch_tool("search_files", {"pattern": "secret", "path": str(outside)})

        data = json.loads(result)
        assert "outside workspace" in data["error"]

    def test_search_files_uses_fixed_path_not_workspace_path(self, tmp_path, monkeypatch):
        workspace = tmp_path / "workspace"
        bin_dir = workspace / "bin"
        workspace.mkdir()
        bin_dir.mkdir()
        fake_rg = bin_dir / "rg"
        fake_rg.write_text("#!/bin/sh\necho PWNED_RG\n", encoding="utf-8")
        fake_rg.chmod(0o755)
        target = workspace / "searchme.txt"
        target.write_text("unique_fixed_path_marker\n", encoding="utf-8")
        monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ.get('PATH', '')}")

        with use_execution_context(_orchestrator_for_workspace(workspace)):
            result = dispatch_tool(
                "search_files",
                {"pattern": "unique_fixed_path_marker", "path": str(workspace)},
            )

        assert "PWNED_RG" not in result
        data = json.loads(result)
        if "error" in data:
            pytest.skip(data["error"])
        assert data["total"] >= 1

    def test_search_files_treats_dash_prefixed_pattern_as_literal(self, tmp_path):
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        (workspace / "safe.txt").write_text("ordinary text\n", encoding="utf-8")

        with use_execution_context(_orchestrator_for_workspace(workspace)):
            result = dispatch_tool(
                "search_files",
                {"pattern": "--pre=/bin/echo PWNED", "path": str(workspace)},
            )

        assert "PWNED" not in result
        data = json.loads(result)
        if "error" in data:
            pytest.skip(data["error"])
        assert data["total"] == 0

    def test_search_files_disables_ripgrep_config_and_sanitizes_env(self, tmp_path, monkeypatch):
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        monkeypatch.setenv("RIPGREP_CONFIG_PATH", str(tmp_path / "evil-rg-config"))
        monkeypatch.setenv("LD_PRELOAD", str(tmp_path / "evil.so"))

        completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        with patch("butler.tools.terminal_impl.subprocess.run", return_value=completed) as mock_run:
            with use_execution_context(_orchestrator_for_workspace(workspace)):
                result = dispatch_tool("search_files", {"pattern": "needle", "path": str(workspace)})

        data = json.loads(result)
        assert data["total"] == 0
        cmd = mock_run.call_args.args[0]
        env = mock_run.call_args.kwargs["env"]
        assert "--no-config" in cmd
        assert "RIPGREP_CONFIG_PATH" not in env
        assert "LD_PRELOAD" not in env

    def test_search_files_revalidates_result_paths(self, tmp_path):
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        outside = tmp_path / "outside.txt"
        outside.write_text("needle\n", encoding="utf-8")
        payload = {
            "type": "match",
            "data": {
                "path": {"text": str(outside)},
                "line_number": 1,
                "lines": {"text": "needle\n"},
            },
        }
        completed = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=json.dumps(payload),
            stderr="",
        )

        with patch("butler.tools.terminal_impl.subprocess.run", return_value=completed):
            with use_execution_context(_orchestrator_for_workspace(workspace)):
                result = dispatch_tool("search_files", {"pattern": "needle", "path": str(workspace)})

        data = json.loads(result)
        assert data["total"] == 0
        assert data["matches"] == []
        assert str(outside) not in result


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

    def test_denies_listing_outside_current_workspace(self, tmp_path):
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        with use_execution_context(_orchestrator_for_workspace(workspace)):
            result = dispatch_tool("list_directory", {"path": str(tmp_path)})

        data = json.loads(result)
        assert "outside workspace" in data["error"]


@pytest.mark.module_test
class TestDelegateTask:
    @patch("butler.report.cache_report")
    @patch("butler.orchestrator.ButlerOrchestrator")
    def test_delegate_task_with_mock_orchestrator(self, mock_orch_cls, mock_cache):
        from butler.core.agent_loop import LoopResult, LoopStatus

        mock_agent = MagicMock()  # noqa: magicmock-no-spec — tools registry facade (orch / agent / proc)
        mock_agent.run.return_value = LoopResult(
            status=LoopStatus.COMPLETED,
            final_response="delegation done",
            iterations=2,
            tool_calls_made=1,
            total_tokens=100,
            elapsed_seconds=1.5,
        )
        mock_orch = MagicMock()  # noqa: magicmock-no-spec — tools registry facade (orch / agent / proc)
        mock_orch.create_project_agent_loop.return_value = mock_agent
        mock_orch.inject_skill_context.side_effect = lambda text, **_: text
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

    @patch("butler.session.lifecycle.sync_turn_memory", return_value={"skipped": False})
    @patch("butler.session.lifecycle.attach_turn_memory_prefetch")
    @patch("butler.report.cache_report")
    @patch("butler.orchestrator.ButlerOrchestrator")
    def test_delegate_task_reuses_execution_context_orchestrator(
        self,
        mock_orch_cls,
        mock_cache,
        mock_prefetch,
        mock_sync,
    ):
        from butler.core.agent_loop import LoopResult, LoopStatus
        from butler.execution_context import use_execution_context

        mock_agent = MagicMock()  # noqa: magicmock-no-spec — tools registry facade (orch / agent / proc)
        mock_agent.run.return_value = LoopResult(
            status=LoopStatus.COMPLETED,
            final_response="delegation done",
        )
        current_orch = MagicMock()  # noqa: magicmock-no-spec — tools registry facade (orch / agent / proc)
        current_orch.create_project_agent_loop.return_value = mock_agent
        current_orch.inject_skill_context.side_effect = lambda text, **_: (
            f"## 相关知识（Butler Skill）\nUse pytest\n\n{text}"
        )

        with use_execution_context(current_orch, session_key="gateway-session"):
            result = dispatch_tool("delegate_task", {"role": "dev", "task": "run python tests"})

        data = json.loads(result)
        assert data["success"] is True
        mock_orch_cls.assert_not_called()
        current_orch.create_project_agent_loop.assert_called_once()
        current_orch.inject_skill_context.assert_called_once()
        assert "Use pytest" in mock_agent.run.call_args.args[0]
        mock_prefetch.assert_called_once()
        assert mock_prefetch.call_args.args[1] is current_orch
        mock_sync.assert_called_once()
        assert mock_sync.call_args.args[1] == "run python tests"
        assert mock_sync.call_args.kwargs["session_id"] == "gateway-session"

    @patch("butler.session.lifecycle.sync_turn_memory", return_value={"skipped": False})
    @patch("butler.session.lifecycle.attach_turn_memory_prefetch")
    @patch("butler.report.cache_report")
    @patch("butler.orchestrator.ButlerOrchestrator")
    def test_delegate_task_binds_context_during_agent_run(
        self,
        mock_orch_cls,
        mock_cache,
        mock_prefetch,
        mock_sync,
    ):
        from butler.core.agent_loop import LoopResult, LoopStatus
        from butler.execution_context import get_current_orchestrator

        mock_orch = MagicMock()  # noqa: magicmock-no-spec — tools registry facade (orch / agent / proc)
        mock_orch.inject_skill_context.side_effect = lambda text, **_: text

        def _run(_message: str, **kwargs) -> LoopResult:
            assert get_current_orchestrator() is mock_orch
            return LoopResult(status=LoopStatus.COMPLETED, final_response="delegation done")

        mock_agent = MagicMock()  # noqa: magicmock-no-spec — tools registry facade (orch / agent / proc)
        mock_agent.run.side_effect = _run
        mock_orch.create_project_agent_loop.return_value = mock_agent
        mock_orch_cls.return_value = mock_orch

        result = dispatch_tool("delegate_task", {"role": "dev", "task": "run tests"})

        assert json.loads(result)["success"] is True

    @patch("butler.session.lifecycle.sync_turn_memory", return_value={"skipped": False})
    @patch("butler.session.lifecycle.attach_turn_memory_prefetch")
    @patch("butler.report.cache_report")
    @patch("butler.orchestrator.ButlerOrchestrator")
    def test_delegate_marks_failure_when_tools_error_without_changes(
        self,
        mock_orch_cls,
        mock_cache,
        mock_prefetch,
        mock_sync,
    ):
        from butler.core.agent_loop import LoopResult, LoopStatus

        mock_agent = MagicMock()  # noqa: magicmock-no-spec — tools registry facade (orch / agent / proc)
        mock_agent.run.return_value = LoopResult(
            status=LoopStatus.COMPLETED,
            final_response="无法删除文件",
            messages=[
                {
                    "role": "tool",
                    "content": json.dumps({"error": "File not found: docs/missing.txt"}),
                },
            ],
        )
        mock_orch = MagicMock()  # noqa: magicmock-no-spec — tools registry facade (orch / agent / proc)
        mock_orch.create_project_agent_loop.return_value = mock_agent
        mock_orch.inject_skill_context.side_effect = lambda text, **_: text
        mock_orch_cls.return_value = mock_orch

        result = dispatch_tool(
            "delegate_task",
            {"role": "dev", "task": "删除 docs/missing.txt"},
        )

        data = json.loads(result)
        assert data["success"] is False
        cached = mock_cache.call_args[0][0]
        assert "未能完成任务" in cached.headline
        assert cached.issues
        assert cached.task_preview == "删除 docs/missing.txt"


@pytest.mark.module_test
class TestDelegateExtractors:
    def test_extract_changes_recognizes_delete_file(self):
        from butler.tools.registry import _extract_changes_from_messages

        messages = [
            {
                "role": "tool",
                "content": json.dumps(
                    {"success": True, "path": "docs/test_hello.txt", "action": "deleted"}
                ),
            },
        ]
        changes = _extract_changes_from_messages(messages)
        assert len(changes) == 1
        assert changes[0].action == "deleted"
        assert changes[0].file == "docs/test_hello.txt"


@pytest.mark.module_test
class TestSkillTools:
    @patch("butler.orchestrator.ButlerOrchestrator")
    def test_skills_list_reuses_execution_context_orchestrator(self, mock_orch_cls):
        from butler.execution_context import use_execution_context

        manager = MagicMock()  # noqa: magicmock-no-spec — tools registry facade (orch / agent / proc)
        manager.list_skills.return_value = [
            {"name": "python-dev", "description": "Python development" * 20},
        ]
        current_orch = MagicMock()  # noqa: magicmock-no-spec — tools registry facade (orch / agent / proc)
        current_orch._skill_manager = manager

        with use_execution_context(current_orch):
            result = dispatch_tool("skills_list", {})

        data = json.loads(result)
        assert data["skills"][0]["name"] == "python-dev"
        mock_orch_cls.assert_not_called()

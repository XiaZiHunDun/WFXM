"""Tests for butler/dev_engine/verify.py — layered verification.

Covers: verify_lint, verify_typecheck, verify_test, verify_build, verify_layered,
_has_tool availability gate, _run_command timeout/not-found handling.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from butler.dev_engine.dev_state import VerifyResult, VerifyStatus
from butler.dev_engine.verify import (
    _load_project_dev_config,
    _run_command,
    verify_build,
    verify_layered,
    verify_lint,
    verify_test,
    verify_typecheck,
)


@pytest.mark.unit
class TestRunCommand:
    def test_success_returns_pass(self, tmp_path: Path):
        result = _run_command(["echo", "ok"], tmp_path, timeout=5, source="echo")
        assert result.status == VerifyStatus.PASS
        assert result.exit_code == 0
        assert result.elapsed_seconds > 0

    def test_failure_returns_fail(self, tmp_path: Path):
        result = _run_command(["python", "-c", "import sys; sys.exit(1)"], tmp_path, timeout=5, source="py")
        assert result.status == VerifyStatus.FAIL
        assert result.exit_code == 1

    def test_timeout_returns_timeout(self, tmp_path: Path):
        result = _run_command(["sleep", "10"], tmp_path, timeout=1, source="sleep")
        assert result.status == VerifyStatus.TIMEOUT

    def test_missing_binary_returns_skip(self, tmp_path: Path):
        result = _run_command(["__nonexistent_tool_xyz__"], tmp_path, timeout=5, source="fake")
        assert result.status == VerifyStatus.SKIP

    def test_diagnostics_populated_on_failure(self, tmp_path: Path):
        code = "import sys; print('Error: foo.py:1:0 invalid syntax', file=sys.stderr); sys.exit(1)"
        result = _run_command(["python", "-c", code], tmp_path, timeout=5, source="test")
        assert result.status == VerifyStatus.FAIL
        assert result.diagnostics is not None


@pytest.mark.unit
class TestVerifyLint:
    def test_skip_when_no_tool(self, tmp_path: Path):
        with patch("butler.dev_engine.verify._has_tool", return_value=False):
            result = verify_lint(tmp_path)
        assert result.status == VerifyStatus.SKIP
        assert "no tool" in result.command.lower()

    def test_calls_ruff_when_available(self, tmp_path: Path):
        with patch("butler.dev_engine.verify._has_tool", side_effect=lambda n: n == "ruff"):
            with patch("butler.dev_engine.verify._run_command", return_value=VerifyResult(status=VerifyStatus.PASS)) as mock_run:
                result = verify_lint(tmp_path)
        assert result.status == VerifyStatus.PASS
        args = mock_run.call_args
        assert "ruff" in args[0][0][0]

    def test_calls_flake8_as_fallback(self, tmp_path: Path):
        def _tool_check(name):
            return name == "flake8"

        with patch("butler.dev_engine.verify._has_tool", side_effect=_tool_check):
            with patch("butler.dev_engine.verify._run_command", return_value=VerifyResult(status=VerifyStatus.PASS)) as mock_run:
                result = verify_lint(tmp_path)
        assert result.status == VerifyStatus.PASS
        args = mock_run.call_args
        assert "flake8" in args[0][0][0]

    def test_passes_specific_files(self, tmp_path: Path):
        with patch("butler.dev_engine.verify._has_tool", return_value=True):
            with patch("butler.dev_engine.verify._run_command", return_value=VerifyResult(status=VerifyStatus.PASS)) as mock_run:
                verify_lint(tmp_path, files=["foo.py", "bar.py"])
        cmd = mock_run.call_args[0][0]
        assert "foo.py" in cmd
        assert "bar.py" in cmd


@pytest.mark.unit
class TestVerifyTypecheck:
    def test_skip_when_no_mypy(self, tmp_path: Path):
        with patch("butler.dev_engine.verify._has_tool", return_value=False):
            result = verify_typecheck(tmp_path)
        assert result.status == VerifyStatus.SKIP

    def test_calls_mypy_when_available(self, tmp_path: Path):
        with patch("butler.dev_engine.verify._has_tool", return_value=True):
            with patch("butler.dev_engine.verify._run_command", return_value=VerifyResult(status=VerifyStatus.PASS)) as mock_run:
                verify_typecheck(tmp_path)
        cmd = mock_run.call_args[0][0]
        assert "mypy" in cmd


@pytest.mark.unit
class TestVerifyTest:
    def test_skip_when_no_pytest(self, tmp_path: Path):
        with patch("butler.dev_engine.verify._has_tool", return_value=False):
            result = verify_test(tmp_path)
        assert result.status == VerifyStatus.SKIP

    def test_uses_default_timeout(self, tmp_path: Path):
        with patch("butler.dev_engine.verify._has_tool", return_value=True):
            with patch("butler.dev_engine.verify._run_command", return_value=VerifyResult(status=VerifyStatus.PASS)) as mock_run:
                verify_test(tmp_path)
        timeout_arg = mock_run.call_args[0][2]
        assert timeout_arg > 0

    def test_passes_custom_test_files(self, tmp_path: Path):
        with patch("butler.dev_engine.verify._has_tool", return_value=True):
            with patch("butler.dev_engine.verify._run_command", return_value=VerifyResult(status=VerifyStatus.PASS)) as mock_run:
                verify_test(tmp_path, test_files=["tests/test_foo.py"])
        cmd = mock_run.call_args[0][0]
        assert "tests/test_foo.py" in cmd


@pytest.mark.unit
class TestProjectDevCommands:
    def test_load_project_dev_config_from_yaml(self, tmp_path: Path):
        (tmp_path / "project.yaml").write_text(
            "dev:\n  test_command: python -m pytest tests/ -q\n  lint_command: 'true'\n"
        )
        dev = _load_project_dev_config(tmp_path)
        assert "test_command" in dev
        assert dev["lint_command"] == "true"

    def test_verify_lint_uses_project_lint_command(self, tmp_path: Path):
        (tmp_path / "project.yaml").write_text('dev:\n  lint_command: "true"\n')
        result = verify_lint(tmp_path)
        assert result.status == VerifyStatus.PASS
        assert result.command == "true"

    def test_verify_test_uses_project_test_command(self, tmp_path: Path):
        (tmp_path / "project.yaml").write_text('dev:\n  test_command: "true"\n')
        result = verify_test(tmp_path)
        assert result.status == VerifyStatus.PASS
        assert result.command == "true"

    def test_project_lint_takes_priority_over_ruff(self, tmp_path: Path):
        (tmp_path / "project.yaml").write_text('dev:\n  lint_command: "true"\n')
        with patch("butler.dev_engine.verify._has_tool", return_value=True):
            with patch("butler.dev_engine.verify._run_command", return_value=VerifyResult(status=VerifyStatus.PASS)) as mock_run:
                verify_lint(tmp_path)
        assert mock_run.call_args[0][0] == ["true"]
        assert mock_run.call_args[1]["env"] is not None

    def test_project_test_appends_test_files(self, tmp_path: Path):
        (tmp_path / "project.yaml").write_text('dev:\n  test_command: "echo test"\n')
        with patch("butler.dev_engine.verify._run_command", return_value=VerifyResult(status=VerifyStatus.PASS)) as mock_run:
            verify_test(tmp_path, test_files=["tests/test_foo.py"])
        assert mock_run.call_args[0][0] == ["echo", "test", "tests/test_foo.py"]

    def test_fallback_lint_when_no_project_yaml(self, tmp_path: Path):
        with patch("butler.dev_engine.verify._has_tool", return_value=False):
            result = verify_lint(tmp_path)
        assert result.status == VerifyStatus.SKIP
        assert "no tool" in result.command.lower()

    def test_quoted_lint_command_parsed_with_shlex(self, tmp_path: Path):
        (tmp_path / "project.yaml").write_text(
            "dev:\n  lint_command: rg 'import pdb|breakpoint()' --count\n"
        )
        with patch("butler.dev_engine.verify._run_command", return_value=VerifyResult(status=VerifyStatus.PASS)) as mock_run:
            verify_lint(tmp_path)
        assert mock_run.call_args[0][0] == ["rg", "import pdb|breakpoint()", "--count"]


@pytest.mark.unit
class TestVerifyBuild:
    def test_skip_when_no_build_system(self, tmp_path: Path):
        result = verify_build(tmp_path)
        assert result.status == VerifyStatus.SKIP

    def test_uses_makefile_when_present(self, tmp_path: Path):
        (tmp_path / "Makefile").write_text("all:\n\techo ok\n")
        with patch("butler.dev_engine.verify._run_command", return_value=VerifyResult(status=VerifyStatus.PASS)) as mock_run:
            verify_build(tmp_path)
        cmd = mock_run.call_args[0][0]
        assert "make" in cmd

    def test_uses_pyproject_when_present(self, tmp_path: Path):
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "test"\n')
        with patch("butler.dev_engine.verify._run_command", return_value=VerifyResult(status=VerifyStatus.PASS)) as mock_run:
            verify_build(tmp_path)
        cmd = mock_run.call_args[0][0]
        assert "py_compile" in " ".join(cmd)

    def test_uses_project_build_command(self, tmp_path: Path):
        (tmp_path / "project.yaml").write_text('dev:\n  build_command: "true"\n')
        result = verify_build(tmp_path)
        assert result.status == VerifyStatus.PASS
        assert result.command == "true"

    def test_project_build_takes_priority_over_makefile(self, tmp_path: Path):
        (tmp_path / "project.yaml").write_text('dev:\n  build_command: "true"\n')
        (tmp_path / "Makefile").write_text("all:\n\techo ok\n")
        with patch("butler.dev_engine.verify._run_command", return_value=VerifyResult(status=VerifyStatus.PASS)) as mock_run:
            verify_build(tmp_path)
        assert mock_run.call_args[0][0] == ["true"]


@pytest.mark.unit
class TestVerifyLayered:
    def test_all_skip_returns_pass(self, tmp_path: Path):
        with patch("butler.dev_engine.verify._has_tool", return_value=False):
            result = verify_layered(tmp_path, levels="lint,typecheck")
        assert result.status == VerifyStatus.PASS

    def test_lint_fail_stops_early(self, tmp_path: Path):
        fail_result = VerifyResult(status=VerifyStatus.FAIL, diagnostics=["error"], exit_code=1)
        with patch("butler.dev_engine.verify.verify_lint", return_value=fail_result):
            with patch("butler.dev_engine.verify.verify_test") as mock_test:
                result = verify_layered(tmp_path, levels="lint,test")
        assert result.status == VerifyStatus.FAIL
        mock_test.assert_not_called()

    def test_timeout_stops_early(self, tmp_path: Path):
        timeout_result = VerifyResult(status=VerifyStatus.TIMEOUT)
        with patch("butler.dev_engine.verify.verify_lint", return_value=timeout_result):
            result = verify_layered(tmp_path, levels="lint,test")
        assert result.status == VerifyStatus.TIMEOUT

    def test_unknown_level_ignored(self, tmp_path: Path):
        with patch("butler.dev_engine.verify._has_tool", return_value=False):
            result = verify_layered(tmp_path, levels="lint,unknown_level")
        assert result.status == VerifyStatus.PASS

    def test_single_level_lint_only(self, tmp_path: Path):
        pass_result = VerifyResult(status=VerifyStatus.PASS)
        with patch("butler.dev_engine.verify.verify_lint", return_value=pass_result) as mock_lint:
            result = verify_layered(tmp_path, levels="lint")
        assert result.status == VerifyStatus.PASS
        mock_lint.assert_called_once()

    def test_multiple_levels_all_pass(self, tmp_path: Path):
        pass_result = VerifyResult(status=VerifyStatus.PASS)
        with patch("butler.dev_engine.verify.verify_lint", return_value=pass_result):
            with patch("butler.dev_engine.verify.verify_test", return_value=pass_result):
                result = verify_layered(tmp_path, levels="lint,test")
        assert result.status == VerifyStatus.PASS
        assert "lint,test" in result.command

"""Layered verification — lint / typecheck / test / build.

Formal model from v4-dev-engine-theory.md §2.5:
  Verify: WorkspaceState × VerifyConfig → VerifyResult
  V1 (lint) → V2 (type) → V3 (test) → V4 (integration) → V5 (build)
"""

from __future__ import annotations

from butler.env_parse import int_env
import logging
import os
import shlex
import subprocess
import time
from pathlib import Path
from typing import Any, cast

from butler.dev_engine.dev_state import VerifyResult, VerifyStatus
from butler.dev_engine.diagnostics import parse_diagnostics

logger = logging.getLogger(__name__)

DEFAULT_VERIFY_TIMEOUT = int_env("BUTLER_DEV_VERIFY_TIMEOUT", 300)


def _project_dev_env() -> dict[str, str]:
    from butler.dev_engine.project_dev_env import project_dev_subprocess_env

    return cast(dict[str, str], project_dev_subprocess_env())


def _load_project_dev_config(workspace: Path) -> dict[str, Any]:
    """Load ``dev:`` block from ``workspace/project.yaml`` when present."""
    from butler.dev_engine.verify_ops import load_project_dev_config_safe

    return cast(dict[str, Any], load_project_dev_config_safe(workspace))


def _argv_from_dev_command(cmd: str, extra_args: list[str] | None = None) -> list[str]:
    argv = shlex.split(cmd.strip())
    if extra_args:
        argv.extend(extra_args)
    return argv


def _run_command(
    cmd: list[str],
    workspace: Path,
    timeout: int,
    source: str,
    *,
    env: dict[str, str] | None = None,
) -> VerifyResult:
    """Run a verification command and parse output."""
    from butler.dev_engine.verify_ops import execute_verify_subprocess

    return execute_verify_subprocess(
        cmd, workspace, timeout, source, env=env,
    )


def _run_project_dev_command(
    workspace: Path,
    cmd: str,
    *,
    timeout: int,
    source: str,
    extra_args: list[str] | None = None,
) -> VerifyResult:
    argv = _argv_from_dev_command(cmd, extra_args)
    if not argv:
        return VerifyResult(status=VerifyStatus.SKIP, command=cmd or "project dev (empty)")
    return _run_command(argv, workspace, timeout, source, env=_project_dev_env())


def verify_lint(
    workspace: Path,
    *,
    files: list[str] | None = None,
    timeout: int = 60,
) -> VerifyResult:
    """V1: Lint / format check."""
    dev = _load_project_dev_config(workspace)
    lint_cmd = str(dev.get("lint_command") or "").strip()
    if lint_cmd:
        return _run_project_dev_command(
            workspace, lint_cmd, timeout=timeout, source="project-lint",
        )

    cmd: list[str]
    if _has_tool("ruff"):
        cmd = ["ruff", "check", "--no-fix"]
        if files:
            cmd.extend(files)
        else:
            cmd.append(".")
        return _run_command(cmd, workspace, timeout, "ruff")

    if _has_tool("flake8"):
        cmd = ["flake8"]
        if files:
            cmd.extend(files)
        return _run_command(cmd, workspace, timeout, "flake8")

    return VerifyResult(status=VerifyStatus.SKIP, command="lint (no tool found)")


def verify_typecheck(
    workspace: Path,
    *,
    files: list[str] | None = None,
    timeout: int = 120,
) -> VerifyResult:
    """V2: Type checking."""
    if _has_tool("mypy"):
        cmd = ["mypy", "--no-error-summary"]
        if files:
            cmd.extend(files)
        else:
            cmd.append(".")
        return _run_command(cmd, workspace, timeout, "mypy")

    return VerifyResult(status=VerifyStatus.SKIP, command="typecheck (no tool found)")


def verify_test(
    workspace: Path,
    *,
    test_files: list[str] | None = None,
    timeout: int | None = None,
) -> VerifyResult:
    """V3: Unit tests."""
    if timeout is None:
        timeout = DEFAULT_VERIFY_TIMEOUT

    dev = _load_project_dev_config(workspace)
    test_cmd = str(dev.get("test_command") or "").strip()
    if test_cmd:
        return _run_project_dev_command(
            workspace,
            test_cmd,
            timeout=timeout,
            source="project-test",
            extra_args=test_files,
        )

    if _has_tool("pytest"):
        cmd = ["python", "-m", "pytest", "-x", "-q", "--tb=short", "--no-header"]
        if test_files:
            cmd.extend(test_files)
        return _run_command(cmd, workspace, timeout, "pytest")

    return VerifyResult(status=VerifyStatus.SKIP, command="test (no tool found)")


def verify_integration(
    workspace: Path,
    *,
    timeout: int | None = None,
) -> VerifyResult:
    """V4: Integration tests — runs tests marked with 'integration' marker."""
    if timeout is None:
        timeout = DEFAULT_VERIFY_TIMEOUT

    if _has_tool("pytest"):
        cmd = ["python", "-m", "pytest", "-x", "-q", "--tb=short", "--no-header", "-m", "integration"]
        return _run_command(cmd, workspace, timeout, "pytest-integration")

    return VerifyResult(status=VerifyStatus.SKIP, command="integration (no pytest)")


def verify_build(
    workspace: Path,
    *,
    timeout: int | None = None,
) -> VerifyResult:
    """V5: Build verification."""
    if timeout is None:
        timeout = DEFAULT_VERIFY_TIMEOUT

    dev = _load_project_dev_config(workspace)
    build_cmd = str(dev.get("build_command") or "").strip()
    if build_cmd:
        return _run_project_dev_command(
            workspace, build_cmd, timeout=timeout, source="project-build",
        )

    if (workspace / "Makefile").exists():
        return _run_command(["make", "-q"], workspace, timeout, "make")

    if (workspace / "pyproject.toml").exists():
        return _run_command(
            ["python", "-m", "py_compile", "__init__.py"],
            workspace, timeout, "python",
        )

    return VerifyResult(status=VerifyStatus.SKIP, command="build (no build system found)")


def verify_layered(
    workspace: Path,
    *,
    files: list[str] | None = None,
    levels: str = "lint,test",
    timeout: int | None = None,
) -> VerifyResult:
    """Run multiple verification levels and return first failure or PASS.

    levels: comma-separated string of "lint", "typecheck", "test", "build"
    """
    if timeout is None:
        timeout = DEFAULT_VERIFY_TIMEOUT

    level_list = [lvl.strip() for lvl in levels.split(",") if lvl.strip()]
    dispatch = {
        "lint": lambda: verify_lint(workspace, files=files, timeout=min(60, timeout)),
        "typecheck": lambda: verify_typecheck(workspace, files=files, timeout=min(120, timeout)),
        "test": lambda: verify_test(workspace, timeout=timeout),
        "integration": lambda: verify_integration(workspace, timeout=timeout),
        "build": lambda: verify_build(workspace, timeout=timeout),
    }

    for level in level_list:
        runner = dispatch.get(level)
        if runner is None:
            continue
        result = runner()
        if result.status == VerifyStatus.FAIL:
            return result
        if result.status == VerifyStatus.TIMEOUT:
            return result

    return VerifyResult(status=VerifyStatus.PASS, command=f"layered({levels})")


def verify_level_for_edit(edited_files: list[str]) -> str:
    """Select verification levels based on which files were edited (DA2).

    Heuristic: test files → lint,test; config files → lint,build;
    source files → lint,test; other → lint.
    """
    if not edited_files:
        return "lint"

    has_test = any(
        "test" in f.lower() or f.endswith("_test.py") or f.startswith("test_")
        for f in edited_files
    )
    has_config = any(
        f.endswith((".toml", ".yaml", ".yml", ".json", ".cfg", "Makefile", "Dockerfile"))
        for f in edited_files
    )
    has_source = any(
        f.endswith((".py", ".js", ".ts", ".go", ".rs", ".java", ".c", ".cpp"))
        for f in edited_files
    )

    levels = ["lint"]
    if has_source or has_test:
        levels.append("test")
    if has_config:
        levels.append("build")
    return ",".join(levels)


def _normalize_edit_path(path: str) -> str:
    return str(path or "").replace("\\", "/").strip().lstrip("./")


def is_docs_markdown_only_edit(edited_files: list[str]) -> bool:
    """True when every edited path is under docs/ and is markdown/text (pilot docs flywheel)."""
    paths = [_normalize_edit_path(p) for p in edited_files if str(p or "").strip()]
    if not paths:
        return False
    return all(
        p.startswith("docs/") and p.endswith((".md", ".markdown", ".txt"))
        for p in paths
    )


def select_auto_verify_levels(
    edited_files: list[str],
    *,
    delegate_category: str = "",
) -> str:
    """Choose verify levels after an edit (edit-scoped docs vs production/full suite)."""
    cat = str(delegate_category or "").strip().lower()
    if cat.startswith("head-to-head"):
        return "test"

    edit_levels = verify_level_for_edit(edited_files)
    if is_docs_markdown_only_edit(edited_files):
        return edit_levels
    prod_levels = ""
    if cat:
        from butler.dev_engine.verify_ops import production_auto_verify_levels_safe

        prod_levels = production_auto_verify_levels_safe(cat)
    return prod_levels or auto_verify_levels() or edit_levels


def auto_verify_levels() -> str:
    """Return the auto-verify levels from env (default: lint,test)."""
    default = os.getenv("BUTLER_DEV_AUTO_VERIFY_LEVELS", "lint,test").strip()
    from butler.dev_engine.verify_ops import effective_dev_auto_verify_levels_safe

    return cast(str, effective_dev_auto_verify_levels_safe(default=default))


def _has_tool(name: str) -> bool:
    """Check if a CLI tool is available on PATH."""
    import shutil

    return shutil.which(name) is not None

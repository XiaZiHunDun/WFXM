"""Tests for projects/LingWen1/novel-factory/tools/validators/validate_all.py."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DISPATCHER = (
    ROOT
    / "projects"
    / "LingWen1"
    / "novel-factory"
    / "tools"
    / "validators"
    / "validate_all.py"
)
REAL_CHAPTER = (
    ROOT
    / "projects"
    / "LingWen1"
    / "novel-factory"
    / "03_内容仓库"
    / "04_正文"
    / "ch001.md"
)
REAL_REVIEWER = (
    ROOT
    / "projects"
    / "LingWen1"
    / "novel-factory"
    / "06_意见仓库"
    / "04_正文_审核"
    / "ch001_审核员A_审核.md"
)
REAL_TEMPLATE = (
    ROOT
    / "projects"
    / "LingWen1"
    / "novel-factory"
    / "01_灵感库"
    / "模板库"
    / "基础层模板.yaml"
)


def _run(*args: str) -> subprocess.CompletedProcess:
    env = {
        "PYTHONPATH": f"{ROOT}/projects/LingWen1/novel-factory/tools:"
                     f"{ROOT}/projects/LingWen1/novel-factory/tools/inspiration:"
                     f"{ROOT}",
    }
    return subprocess.run(
        [sys.executable, str(DISPATCHER), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**__import__("os").environ, **env},
    )


@pytest.mark.unit
def test_dispatcher_delegates_to_writer_suite():
    proc = _run("writer", str(REAL_CHAPTER))
    assert proc.returncode == 0, f"stderr:\n{proc.stderr}\nstdout:\n{proc.stdout}"
    assert "validated" in proc.stdout


@pytest.mark.unit
def test_dispatcher_delegates_to_reviewer_suite():
    proc = _run("reviewer", str(REAL_REVIEWER))
    assert proc.returncode == 0, f"stderr:\n{proc.stderr}\nstdout:\n{proc.stdout}"


@pytest.mark.unit
def test_dispatcher_delegates_to_inspiration_suite():
    proc = _run("inspiration", str(REAL_TEMPLATE))
    assert proc.returncode == 0, f"stderr:\n{proc.stderr}\nstdout:\n{proc.stdout}"


@pytest.mark.unit
def test_dispatcher_rejects_unknown_suite():
    proc = _run("bogus", str(REAL_CHAPTER))
    assert proc.returncode == 2
    assert "invalid choice" in proc.stderr.lower() or "bogus" in proc.stderr
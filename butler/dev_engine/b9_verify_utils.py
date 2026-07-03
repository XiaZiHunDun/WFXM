"""Shared verify helpers for B9 benchmark tasks."""

from __future__ import annotations

from pathlib import Path


def pytest_verify(ws: Path, rel_test: str = "test_b9.py") -> tuple[bool, str]:
    from butler.dev_engine.b9_verify_utils_ops import run_pytest_subprocess

    code, stdout, stderr = run_pytest_subprocess(ws, rel_test)
    if code == -1 and not stdout and stderr:
        return False, stderr
    if code == 0:
        return True, "pytest passed"
    tail = (stdout + stderr)[-500:]
    return False, tail or "pytest failed"


__all__ = ["pytest_verify"]

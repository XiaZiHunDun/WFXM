"""Shared verify helpers for B9 benchmark tasks."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def pytest_verify(ws: Path, rel_test: str = "test_b9.py") -> tuple[bool, str]:
    tf = ws / rel_test
    if not tf.is_file():
        return False, f"{rel_test} missing"
    env = {**os.environ, "PYTHONPATH": str(ws)}
    try:
        r = subprocess.run(
            [sys.executable, "-m", "pytest", str(tf), "-q", "--tb=line"],
            cwd=str(ws),
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
        )
    except Exception as exc:
        return False, str(exc)
    if r.returncode == 0:
        return True, "pytest passed"
    tail = (r.stdout + r.stderr)[-500:]
    return False, tail or "pytest failed"


__all__ = ["pytest_verify"]

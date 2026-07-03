"""B9 verify subprocess best-effort helpers (P0-A)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def run_pytest_subprocess(ws: Path, rel_test: str, *, timeout: int = 30) -> tuple[int, str, str]:
    """Run pytest; return (returncode, stdout, stderr). On failure return (-1, '', error)."""
    tf = ws / rel_test
    if not tf.is_file():
        return -1, "", f"{rel_test} missing"
    env = {**os.environ, "PYTHONPATH": str(ws)}
    try:
        r = subprocess.run(
            [sys.executable, "-m", "pytest", str(tf), "-q", "--tb=line"],
            cwd=str(ws),
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
    except Exception as exc:
        return -1, "", str(exc)
    return r.returncode, r.stdout, r.stderr

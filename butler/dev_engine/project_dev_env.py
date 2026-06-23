"""Subprocess environment for project.yaml dev commands (VERIFY + /测试)."""

from __future__ import annotations

import os
from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def project_dev_subprocess_env() -> dict[str, str]:
    """Inherit Butler process env; force repo root on PYTHONPATH."""
    env = dict(os.environ)
    env["PYTHONPATH"] = str(repo_root())
    return env


__all__ = ["project_dev_subprocess_env", "repo_root"]

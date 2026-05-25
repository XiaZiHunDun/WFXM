"""Git helpers for experiment ledger (read-only by default)."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from butler.env_parse import env_truthy

logger = logging.getLogger(__name__)


def current_git_sha(workspace: Path) -> str:
    ws = Path(workspace).expanduser().resolve()
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(ws),
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.debug("git rev-parse failed: %s", exc)
        return ""
    if proc.returncode != 0:
        return ""
    return (proc.stdout or "").strip()[:40]


def experiment_git_reset_enabled() -> bool:
    return env_truthy("BUTLER_EXPERIMENT_GIT_RESET", default=False)


def git_reset_hard(workspace: Path, sha: str) -> tuple[bool, str]:
    """Reset workspace to *sha* when BUTLER_EXPERIMENT_GIT_RESET=1 (CLI only)."""
    if not experiment_git_reset_enabled():
        return False, "BUTLER_EXPERIMENT_GIT_RESET=0（禁止自动 reset）"
    target = str(sha or "").strip()
    if not target:
        return False, "缺少 git sha"
    ws = Path(workspace).expanduser().resolve()
    try:
        proc = subprocess.run(
            ["git", "reset", "--hard", target],
            cwd=str(ws),
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()[:300]
        return False, err or f"git reset 失败 code={proc.returncode}"
    return True, f"已 reset 到 {target[:12]}"


__all__ = [
    "current_git_sha",
    "experiment_git_reset_enabled",
    "git_reset_hard",
]

"""Butler System v4 — 自建 Agent Loop + 微信 Gateway 管家。

提供：用户→管家→项目的层次结构、分层记忆、Skill自动合并、多角色模型配置。
"""

from __future__ import annotations

import datetime
import logging
import subprocess
import sys

__version__ = "4.0.0"

_logger = logging.getLogger(__name__)

_git_sha: str | None = None
_start_time: datetime.datetime | None = None


def _resolve_git_sha() -> str:
    global _git_sha
    if _git_sha is not None:
        return _git_sha
    try:
        _git_sha = (
            subprocess.check_output(
                ["git", "rev-parse", "--short", "HEAD"],
                stderr=subprocess.DEVNULL,
                timeout=3,
            )
            .decode()
            .strip()
        )
    except Exception:
        _git_sha = "unknown"
    return _git_sha


def get_build_identity() -> dict[str, str]:
    """Return version, git SHA, python version, and start time for diagnostics."""
    global _start_time
    if _start_time is None:
        _start_time = datetime.datetime.now(tz=datetime.timezone.utc)
    sha = _resolve_git_sha()
    return {
        "version": __version__,
        "git_sha": sha,
        "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "python_path": sys.executable,
        "start_time": _start_time.isoformat(),
    }


def format_build_identity_line() -> str:
    info = get_build_identity()
    return f"Butler v{info['version']} (commit={info['git_sha']}, python={info['python']})"


def mark_start_time() -> None:
    """Record process start time (call once at gateway/CLI entry)."""
    global _start_time
    _start_time = datetime.datetime.now(tz=datetime.timezone.utc)

"""Hermes vendored runtime paths (Gateway subprocess fallback only).

Butler 主路径不 import `agent` / `run_agent`。仅 `--hermes-fallback` 子进程使用 ``vendor/hermes-agent/``。
"""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_HERMES_ROOT = _REPO_ROOT / "vendor" / "hermes-agent"


def hermes_repo_root() -> Path:
    """Directory used as cwd for `hermes gateway run` subprocess."""
    if not (_HERMES_ROOT / "hermes_cli").is_dir():
        raise FileNotFoundError(
            f"Hermes vendored tree missing: {_HERMES_ROOT} (expected hermes_cli/). "
            "Run from repo root after checkout."
        )
    return _HERMES_ROOT


def hermes_cli_main() -> Path:
    return hermes_repo_root() / "hermes_cli" / "main.py"

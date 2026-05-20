"""Hermes vendored runtime paths (Gateway subprocess fallback only).

Butler 主路径不 import `agent` / `run_agent`。仅 `--hermes-fallback` 子进程需要定位 Hermes 树。
未来迁仓目标：`vendor/hermes-agent/`（见 docs/architecture/hermes-decoupling.md）。
"""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_VENDOR_ROOT = _REPO_ROOT / "vendor" / "hermes-agent"


def hermes_repo_root() -> Path:
    """Directory used as cwd for `hermes gateway run` subprocess."""
    if (_VENDOR_ROOT / "hermes_cli").is_dir():
        return _VENDOR_ROOT
    return _REPO_ROOT


def hermes_cli_main() -> Path:
    return hermes_repo_root() / "hermes_cli" / "main.py"

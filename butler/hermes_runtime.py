"""Hermes vendored tree location (frozen reference under ``vendor/hermes-agent/``).

Butler 产品路径不启动 Hermes 子进程；本模块仅保留供历史脚本或测试引用 vendor 路径。
"""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_HERMES_ROOT = _REPO_ROOT / "vendor" / "hermes-agent"


def hermes_repo_root() -> Path:
    if not (_HERMES_ROOT / "hermes_cli").is_dir():
        raise FileNotFoundError(
            f"Hermes vendored tree missing: {_HERMES_ROOT} (expected hermes_cli/)."
        )
    return _HERMES_ROOT


def hermes_cli_main() -> Path:
    return hermes_repo_root() / "hermes_cli" / "main.py"

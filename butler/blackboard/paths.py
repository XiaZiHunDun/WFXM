"""黑板路径常量与 shift_id 序号计算。

使用 PEP 562 模块级 __getattr__ 实现懒求值，让 `from butler.blackboard import paths as bb_paths; bb_paths.BLACKBOARD_DIR`
这样的属性访问在每次调用时重新从环境变量 `BLACKBOARD_ROOT` 或 cwd 计算。
"""

from __future__ import annotations

import os
import re
from pathlib import Path


def _root() -> Path:
    """黑板根目录：优先用 BLACKBOARD_ROOT 环境变量，否则 CWD/.blackboard。"""
    env = os.environ.get("BLACKBOARD_ROOT")
    return Path(env) if env else Path.cwd() / ".blackboard"


def _paths() -> dict[str, Path]:
    root = _root()
    return {
        "BLACKBOARD_DIR": root,
        "README_PATH": root / "README.md",
        "STATE_PATH": root / "state.md",
        "LOG_PATH": root / "log.md",
        "SHIFTS_DIR": root / "shifts",
        "TASKS_DIR": root / "tasks",
        "BACKLOG_PATH": root / "tasks" / "backlog.yaml",
        "CLAIMS_DIR": root / "tasks" / "claims",
    }


def __getattr__(name: str):
    paths = _paths()
    if name in paths:
        return paths[name]
    raise AttributeError(f"module 'butler.blackboard.paths' has no attribute {name!r}")


def configure_root(root: Path) -> None:
    """CLI 子命令 --root 时调用；通过设置 BLACKBOARD_ROOT 影响后续 path 访问。"""
    os.environ["BLACKBOARD_ROOT"] = str(root)


_SHIFT_FILE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})-([a-z\-]+)-(\d{3})\.md$")


def next_shift_seq(agent: str, date: str) -> int:
    """返回指定 agent+date 下次应使用的 3 位序号（1-based）。"""
    shifts_dir = _paths()["SHIFTS_DIR"]
    max_seq = 0
    if shifts_dir.is_dir():
        for p in shifts_dir.iterdir():
            m = _SHIFT_FILE_RE.match(p.name)
            if not m:
                continue
            if m.group(1) == date and m.group(2) == agent:
                max_seq = max(max_seq, int(m.group(3)))
    return max_seq + 1


def new_shift_id(agent: str, date: str) -> str:
    """生成 shift_id：`YYYY-MM-DD-<agent>-<NNN>`。"""
    return f"{date}-{agent}-{next_shift_seq(agent, date):03d}"
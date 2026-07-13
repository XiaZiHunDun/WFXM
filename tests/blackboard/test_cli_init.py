"""CLI init 命令测试：从零建黑板目录。"""

from __future__ import annotations

import os
import subprocess
import sys


def test_cli_init_creates_layout(tmp_path):
    """但CLI init 命令在 tmp_path 建完整布局（--root 即黑板目录本身）。"""
    env = {**os.environ, "PYTHONPATH": "."}
    code = subprocess.run(
        [sys.executable, "-m", "butler.main", "blackboard", "init",
         "--root", str(tmp_path)],
        capture_output=True, text=True,
        env=env,
        cwd="/home/ailearn/projects/WFXM",
    )
    assert code.returncode == 0, code.stderr
    assert (tmp_path / "README.md").exists()
    assert (tmp_path / "state.md").exists()
    assert (tmp_path / "log.md").exists()
    assert (tmp_path / "shifts").is_dir()
    assert (tmp_path / "tasks" / "backlog.yaml").exists()
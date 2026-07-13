import os
import subprocess
import sys


def test_cli_sync_runs(tmp_butler_home, tmp_blackboard):
    bb = tmp_blackboard
    code = subprocess.run(
        [sys.executable, "-m", "butler.main", "blackboard", "sync-todos",
         "--root", str(bb)],
        capture_output=True, text=True,
        env={**os.environ, "PYTHONPATH": ".", "BUTLER_HOME": str(tmp_butler_home)},
        cwd="/home/ailearn/projects/WFXM",
    )
    assert code.returncode == 0, code.stderr
    assert "synced backlog" in code.stdout
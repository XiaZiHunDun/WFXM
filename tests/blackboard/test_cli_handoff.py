import os
import subprocess
import sys


def test_handoff_runs(tmp_blackboard):
    code = subprocess.run(
        [sys.executable, "-m", "butler.main", "blackboard", "handoff",
         "--root", str(tmp_blackboard)],
        capture_output=True, text=True,
        env={**os.environ, "PYTHONPATH": "."},
        cwd="/home/ailearn/projects/WFXM",
    )
    assert code.returncode == 0, code.stderr
    assert "交接包" in code.stdout
import os
import subprocess
import sys

from butler.blackboard.shift_io import write_shift_card
from butler.blackboard.schema import ShiftCard, SessionWindow


def test_audit_task(tmp_blackboard):
    write_shift_card(ShiftCard(
        shift_id="2026-07-13-claude-code-001", agent="claude-code",
        session_window=SessionWindow(start="2026-07-13T09:00:00+08:00"),
        intent="audit test", scope=["tests/"], read_at_start=[".blackboard/README.md"],
        claim_ref="tasks/claims/P1-%234.yaml", schema_version=1,
    ), body="")
    code = subprocess.run(
        [sys.executable, "-m", "butler.main", "blackboard", "audit",
         "--task", "P1-#4", "--root", str(tmp_blackboard)],
        capture_output=True, text=True,
        env={**os.environ, "PYTHONPATH": "."},
        cwd="/home/ailearn/projects/WFXM",
    )
    assert code.returncode == 0, code.stderr
    assert "2026-07-13-claude-code-001" in code.stdout
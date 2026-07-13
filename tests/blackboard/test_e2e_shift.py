"""E2E：模拟 Agent A 班次 → Agent B 接手 → 验证交接。"""

from __future__ import annotations

import subprocess
import sys
import os


def test_e2e_two_agents(tmp_path):
    """两个 agent 完整跑一次班次：A 写卡 → B 读 + 接手。"""
    bb = tmp_path / ".blackboard"
    bb.mkdir()
    (bb / "shifts").mkdir()
    (bb / "tasks" / "claims").mkdir(parents=True)
    (bb / "state.md").write_text("# Test state\n_last_synced: init_\n_last_shift: (none)_\n")
    (bb / "log.md").write_text("# Test log\n\n---\n\n")
    (bb / "tasks" / "backlog.yaml").write_text(
        "schema_version: 1\nlast_updated: 2026-07-13T00:00:00+08:00\n"
        "tasks:\n  - id: P1-#4\n    title: x\n    priority: P1\n    status: open\n"
    )

    env = {**os.environ, "PYTHONPATH": ".", "BLACKBOARD_AGENT": "claude-code"}
    cwd = "/home/ailearn/projects/WFXM"

    card_path = bb / "shifts" / "2026-07-13-claude-code-001.md"
    card_path.write_text(
        "---\n"
        "shift_id: 2026-07-13-claude-code-001\n"
        "agent: claude-code\n"
        "session_window:\n  start: 2026-07-13T09:00:00+08:00\n  end: 2026-07-13T11:00:00+08:00\n"
        "intent: 'e2e test'\n"
        "scope: [tests/]\n"
        "read_at_start: [.blackboard/README.md]\n"
        "schema_version: 1\n"
        "---\n\n"
        "body\n"
    )

    r = subprocess.run(
        [sys.executable, "-m", "butler.main", "blackboard", "validate",
         "--shift-id", "2026-07-13-claude-code-001", "--root", str(bb)],
        capture_output=True, text=True, env=env, cwd=cwd,
    )
    assert r.returncode == 0, r.stderr
    assert "OK 2026-07-13-claude-code-001" in r.stdout

    r = subprocess.run(
        [sys.executable, "-m", "butler.main", "blackboard", "snapshot",
         "--root", str(bb)],
        capture_output=True, text=True, env=env, cwd=cwd,
    )
    assert r.returncode == 0, r.stderr
    assert "_last_shift: 2026-07-13-claude-code-001_" in (bb / "state.md").read_text()

    r = subprocess.run(
        [sys.executable, "-m", "butler.main", "blackboard", "handoff",
         "--root", str(bb)],
        capture_output=True, text=True, env=env, cwd=cwd,
    )
    assert r.returncode == 0, r.stderr
    assert "2026-07-13-claude-code-001" in r.stdout
    assert "e2e test" in r.stdout

    from butler.blackboard.integrations.claude_session_end import check_today_shift
    assert check_today_shift("claude-code", "2026-07-13") is None
"""黑板测试 fixture：每个测试一个临时 .blackboard/。"""

from __future__ import annotations

import pytest


@pytest.fixture
def tmp_blackboard(tmp_path, monkeypatch):
    """建临时 .blackboard/ 并 monkeypatch CWD；返回路径。"""
    bb = tmp_path / ".blackboard"
    (bb / "shifts").mkdir(parents=True)
    (bb / "tasks" / "claims").mkdir(parents=True)
    (bb / "README.md").write_text("# Test blackboard\n")
    (bb / "state.md").write_text("# Test state\n_last_synced: test_\n_last_shift: (none)_\n")
    (bb / "log.md").write_text("# Test log\n\n---\n\n")
    monkeypatch.chdir(tmp_path)
    return bb
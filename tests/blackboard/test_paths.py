"""paths 模块测试。"""

from __future__ import annotations

import pytest

from butler.blackboard import paths as bb_paths
from butler.blackboard.paths import new_shift_id, next_shift_seq


def test_constants_are_paths(tmp_blackboard):
    assert bb_paths.BLACKBOARD_DIR.exists()
    assert bb_paths.README_PATH.exists()
    assert bb_paths.STATE_PATH.exists()
    assert bb_paths.LOG_PATH.exists()
    assert bb_paths.SHIFTS_DIR.is_dir()
    assert bb_paths.TASKS_DIR.is_dir()
    assert bb_paths.CLAIMS_DIR.is_dir()


def test_next_shift_seq_empty(tmp_blackboard):
    assert next_shift_seq("claude-code", "2026-07-13") == 1


def test_next_shift_seq_existing(tmp_blackboard):
    (bb_paths.SHIFTS_DIR / "2026-07-13-claude-code-001.md").write_text("x")
    (bb_paths.SHIFTS_DIR / "2026-07-13-claude-code-002.md").write_text("x")
    assert next_shift_seq("claude-code", "2026-07-13") == 3


def test_next_shift_seq_other_agent(tmp_blackboard):
    (bb_paths.SHIFTS_DIR / "2026-07-13-cursor-001.md").write_text("x")
    assert next_shift_seq("claude-code", "2026-07-13") == 1


def test_new_shift_id(tmp_blackboard):
    sid = new_shift_id("claude-code", "2026-07-13")
    assert sid == "2026-07-13-claude-code-001"
"""state_io：state.md 读写 + log.md append。"""

from __future__ import annotations

from butler.blackboard.state_io import (
    read_state_meta,
    update_state_meta,
    append_log_entry,
)


def test_state_meta_roundtrip(tmp_blackboard):
    update_state_meta(last_synced="2026-07-13 17:30", last_shift="2026-07-13-claude-code-001")
    meta = read_state_meta()
    assert meta.last_synced == "2026-07-13 17:30"
    assert meta.last_shift == "2026-07-13-claude-code-001"


def test_append_log_entry(tmp_blackboard):
    initial = tmp_blackboard.joinpath("log.md").read_text()
    append_log_entry("2026-07-13-claude-code-001", "claude-code", "测试摘要")
    after = tmp_blackboard.joinpath("log.md").read_text()
    assert "2026-07-13-claude-code-001" in after
    assert "claude-code" in after
    assert "测试摘要" in after
    assert after.startswith(initial)


def test_append_preserves_existing(tmp_blackboard):
    append_log_entry("2026-07-13-claude-code-001", "claude-code", "first")
    append_log_entry("2026-07-13-cursor-002", "cursor", "second")
    text = tmp_blackboard.joinpath("log.md").read_text()
    assert "2026-07-13-claude-code-001" in text
    assert text.index("2026-07-13-cursor-002") > text.index("2026-07-13-claude-code-001")
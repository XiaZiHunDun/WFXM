"""handoff：交接包生成。"""

from __future__ import annotations

from butler.blackboard.handoff import build_handoff
from butler.blackboard.shift_io import write_shift_card
from butler.blackboard.schema import SessionWindow, ShiftCard


def _card(shift_id: str, intent: str) -> ShiftCard:
    return ShiftCard(
        shift_id=shift_id,
        agent="claude-code",
        session_window=SessionWindow(
            start=shift_id[:10] + "T09:00:00+08:00",
            end=shift_id[:10] + "T11:00:00+08:00",
        ),
        intent=intent,
        scope=["tests/"],
        read_at_start=[".blackboard/README.md"],
        schema_version=1,
    )


def test_handoff_includes_recent_shifts(tmp_blackboard):
    write_shift_card(_card("2026-07-13-claude-code-001", "first"), body="")
    write_shift_card(_card("2026-07-13-claude-code-002", "second"), body="")
    pkg = build_handoff()
    assert "2026-07-13-claude-code-001" in pkg
    assert "2026-07-13-claude-code-002" in pkg


def test_handoff_starts_with_readme(tmp_blackboard):
    pkg = build_handoff()
    assert ".blackboard/README.md" in pkg or "README" in pkg
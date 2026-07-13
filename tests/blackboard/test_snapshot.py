"""snapshot：从 shifts/ + backlog.yaml + claims/ 派生 state.md 摘要。"""

from __future__ import annotations

from butler.blackboard.snapshot import build_snapshot_markdown, render_snapshot
from butler.blackboard.shift_io import write_shift_card
from butler.blackboard.schema import (
    SessionWindow,
    ShiftCard,
)


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


def test_render_snapshot_includes_meta(tmp_blackboard):
    write_shift_card(_card("2026-07-13-claude-code-001", "first"), body="")
    md = render_snapshot()
    assert "_last_synced:" in md
    assert "_last_shift: 2026-07-13-claude-code-001_" in md


def test_render_snapshot_includes_recent_shifts(tmp_blackboard):
    write_shift_card(_card("2026-07-13-claude-code-001", "first"), body="")
    write_shift_card(_card("2026-07-13-claude-code-002", "second"), body="")
    md = render_snapshot()
    assert "2026-07-13-claude-code-001" in md
    assert "2026-07-13-claude-code-002" in md
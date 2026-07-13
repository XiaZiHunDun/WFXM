"""session-end 提醒：检测今日是否缺班次卡。"""

from __future__ import annotations

from butler.blackboard.integrations.claude_session_end import check_today_shift
from butler.blackboard.shift_io import write_shift_card
from butler.blackboard.schema import ShiftCard, SessionWindow


def test_no_cards_warns(tmp_blackboard):
    msg = check_today_shift(agent="claude-code", date="2026-07-13")
    assert msg is not None
    assert "缺班次卡" in msg


def test_card_exists_no_warning(tmp_blackboard):
    write_shift_card(ShiftCard(
        shift_id="2026-07-13-claude-code-001", agent="claude-code",
        session_window=SessionWindow(start="2026-07-13T09:00:00+08:00"),
        intent="x", scope=["tests/"], read_at_start=[".blackboard/README.md"],
        schema_version=1,
    ), body="")
    msg = check_today_shift(agent="claude-code", date="2026-07-13")
    assert msg is None
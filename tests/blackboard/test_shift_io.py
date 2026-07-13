"""shift_io：写班次卡到 shifts/，含 frontmatter + body。"""

from __future__ import annotations

import pytest

from butler.blackboard.shift_io import write_shift_card, list_shift_cards
from butler.blackboard.schema import ShiftCard, SessionWindow


def _make_card(**overrides) -> ShiftCard:
    defaults = dict(
        shift_id="2026-07-13-claude-code-001",
        agent="claude-code",
        session_window=SessionWindow(start="2026-07-13T09:00:00+08:00"),
        intent="测试",
        scope=["tests/"],
        read_at_start=[".blackboard/README.md"],
        schema_version=1,
    )
    defaults.update(overrides)
    return ShiftCard(**defaults)


def test_write_creates_file(tmp_blackboard):
    card = _make_card()
    body = "## 详细叙述\n测试 body"
    path = write_shift_card(card, body=body)
    assert path.exists()
    assert path.name == "2026-07-13-claude-code-001.md"


def test_write_content_roundtrip(tmp_blackboard):
    card = _make_card()
    body = "## 详细\n内容"
    path = write_shift_card(card, body=body)
    text = path.read_text()
    assert text.startswith("---\n")
    assert "intent: 测试" in text
    assert "## 详细\n内容" in text


def test_write_refuses_collision(tmp_blackboard):
    card = _make_card()
    write_shift_card(card, body="first")
    with pytest.raises(Exception):
        write_shift_card(card, body="dup")


def test_list_shift_cards_empty(tmp_blackboard):
    assert list_shift_cards() == []


def test_list_shift_cards_sorted(tmp_blackboard):
    write_shift_card(_make_card(shift_id="2026-07-13-claude-code-002"), body="")
    write_shift_card(_make_card(shift_id="2026-07-13-claude-code-001"), body="")
    cards = list_shift_cards()
    assert [c.shift_id for c in cards] == ["2026-07-13-claude-code-001", "2026-07-13-claude-code-002"]
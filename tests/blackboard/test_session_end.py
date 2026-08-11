"""session-end 提醒：检测今日是否缺班次卡；strict 模式为 hard gate。"""

from __future__ import annotations

from datetime import date

from butler.blackboard.integrations.claude_session_end import check_today_shift, main
from butler.blackboard.shift_io import write_shift_card
from butler.blackboard.schema import ShiftCard, SessionWindow

_TODAY = date.today().isoformat()


def test_no_cards_warns(tmp_blackboard):
    msg = check_today_shift(agent="claude-code", date=_TODAY)
    assert msg is not None
    assert "缺班次卡" in msg


def test_card_exists_no_warning(tmp_blackboard):
    write_shift_card(ShiftCard(
        shift_id=f"{_TODAY}-claude-code-001", agent="claude-code",
        session_window=SessionWindow(start=f"{_TODAY}T09:00:00+08:00"),
        intent="x", scope=["tests/"], read_at_start=[".blackboard/README.md"],
        schema_version=1,
    ), body="")
    msg = check_today_shift(agent="claude-code", date=_TODAY)
    assert msg is None


def test_main_soft_missing_reminds_but_returns_zero(tmp_blackboard, monkeypatch, capsys):
    """非 strict 模式：缺卡仅 stderr 提醒，exit 0。"""
    monkeypatch.delenv("BLACKBOARD_STRICT", raising=False)
    monkeypatch.setenv("BLACKBOARD_AGENT", "claude-code")
    rc = main()
    assert rc == 0
    err = capsys.readouterr().err
    assert "缺班次卡" in err


def test_main_strict_missing_blocks(tmp_blackboard, monkeypatch, capsys):
    """strict 模式：缺卡 exit 2，stderr 提醒。"""
    monkeypatch.setenv("BLACKBOARD_STRICT", "1")
    monkeypatch.setenv("BLACKBOARD_AGENT", "claude-code")
    rc = main()
    assert rc == 2
    err = capsys.readouterr().err
    assert "缺班次卡" in err


def test_main_strict_valid_passes(tmp_blackboard, monkeypatch, capsys):
    """strict 模式：今日有合法卡，validate 通过 → exit 0。"""
    write_shift_card(ShiftCard(
        shift_id=f"{_TODAY}-claude-code-001", agent="claude-code",
        session_window=SessionWindow(start=f"{_TODAY}T09:00:00+08:00"),
        intent="strict-mode-test", scope=["tests/"],
        read_at_start=[".blackboard/README.md"], schema_version=1,
    ), body="")
    monkeypatch.setenv("BLACKBOARD_STRICT", "1")
    monkeypatch.setenv("BLACKBOARD_AGENT", "claude-code")
    rc = main()
    assert rc == 0
    err = capsys.readouterr().err
    assert "缺班次卡" not in err


def test_main_strict_invalid_blocks(tmp_blackboard, monkeypatch, capsys):
    """strict 模式：今日卡存在但 validate 失败（非法 enum）→ exit 2。"""
    card_path = tmp_blackboard / "shifts" / f"{_TODAY}-claude-code-001.md"
    card_path.write_text(
        "---\n"
        f"shift_id: {_TODAY}-claude-code-001\n"
        "agent: bogus-agent\n"  # 非法枚举
        f"session_window:\n  start: {_TODAY}T09:00:00+08:00\n"
        "intent: x\nscope: [tests/]\nread_at_start: [.blackboard/README.md]\n"
        "schema_version: 1\n"
        "---\n\nbody\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("BLACKBOARD_STRICT", "1")
    monkeypatch.setenv("BLACKBOARD_AGENT", "claude-code")
    rc = main()
    assert rc == 2
    err = capsys.readouterr().err
    assert "validate" in err.lower() or "validation" in err.lower() or "失败" in err or "缺" in err
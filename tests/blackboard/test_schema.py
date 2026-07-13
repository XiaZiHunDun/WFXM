"""Pydantic schema 测试：合法 + 非法输入都覆盖。"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from butler.blackboard.schema import (
    BacklogTask,
    Claim,
    ClaimStatus,
    Priority,
    ProducedItem,
    SessionWindow,
    ShiftCard,
    TaskStatus,
)


def test_shift_card_minimal_valid():
    """最小必填字段通过。"""
    card = ShiftCard(
        shift_id="2026-07-13-claude-001",
        agent="claude-code",
        session_window=SessionWindow(start="2026-07-13T09:00:00+08:00"),
        intent="测试最小字段",
        scope=["tests/blackboard/"],
        read_at_start=[".blackboard/README.md"],
        schema_version=1,
    )
    assert card.shift_id == "2026-07-13-claude-001"
    assert card.session_window.end is None


def test_shift_card_full_valid():
    """完整字段通过。"""
    card = ShiftCard(
        shift_id="2026-07-13-claude-001",
        agent="claude-code",
        session_window=SessionWindow(
            start="2026-07-13T09:00:00+08:00",
            end="2026-07-13T11:30:00+08:00",
        ),
        intent="完整字段",
        scope=["tests/blackboard/", "butler/blackboard/"],
        read_at_start=[".blackboard/state.md"],
        produced=[
            ProducedItem(type="commit", ref="abc1234", summary="feat: x"),
            ProducedItem(type="doc", ref="docs/x.md"),
        ],
        unresolved=["tests/gateway 63 pre-existing fail"],
        next_shift_recommendation={"agent": "cursor", "reason": "diff 走读", "blocked_by": []},
        claim_ref="tasks/claims/P1-#4.yaml",
        schema_version=1,
    )
    assert len(card.produced) == 2


def test_shift_card_missing_required():
    """缺 intent 失败。"""
    with pytest.raises(ValidationError) as exc:
        ShiftCard(
            shift_id="2026-07-13-claude-001",
            agent="claude-code",
            session_window=SessionWindow(start="2026-07-13T09:00:00+08:00"),
            scope=["tests/"],
            read_at_start=[".blackboard/README.md"],
            schema_version=1,
        )
    assert "intent" in str(exc.value)


def test_shift_card_invalid_agent():
    """agent 不在枚举内失败。"""
    with pytest.raises(ValidationError) as exc:
        ShiftCard(
            shift_id="2026-07-13-unknown-001",
            agent="unknown-agent-xyz",
            session_window=SessionWindow(start="2026-07-13T09:00:00+08:00"),
            intent="x",
            scope=["tests/"],
            read_at_start=[".blackboard/README.md"],
            schema_version=1,
        )
    assert "agent" in str(exc.value)


def test_backlog_task_valid():
    task = BacklogTask(
        id="P1-#4",
        title="x",
        priority=Priority.P1,
        status=TaskStatus.OPEN,
    )
    assert task.id == "P1-#4"
    assert task.priority == Priority.P1
    assert task.status == TaskStatus.OPEN


def test_claim_valid():
    claim = Claim(
        task_id="P1-#4",
        claimed_by="claude-code",
        claimed_at="2026-07-13T09:00:00+08:00",
        status=ClaimStatus.CLAIMED,
    )
    assert claim.status == ClaimStatus.CLAIMED
    assert claim.handoff_to is None
"""Turn-based compaction tail selection and overflow replay."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from butler.core.context_compressor import SUMMARY_PREFIX, compress_messages
from butler.core.turn_compaction import (
    _strategy_label,
    append_overflow_replay,
    find_overflow_replay_user,
    group_messages_into_turns,
    preserve_recent_token_budget,
    select_tail_start_index,
    split_head_tail_turns,
)


def _turn(user: str, assistant: str = "") -> list[dict]:
    msgs = [{"role": "user", "content": user}]
    if assistant:
        msgs.append({"role": "assistant", "content": assistant})
    return msgs


@pytest.mark.unit
def test_group_messages_into_turns_skips_compaction_summary():
    rest = [
        {"role": "user", "content": SUMMARY_PREFIX + "old"},
        {"role": "user", "content": "task a"},
        {"role": "assistant", "content": "ok a"},
        {"role": "user", "content": "task b"},
        {"role": "assistant", "content": "ok b"},
    ]
    turns = group_messages_into_turns(rest)
    assert len(turns) == 2
    assert rest[turns[0].start]["content"] == "task a"
    assert rest[turns[1].start]["content"] == "task b"


@pytest.mark.unit
def test_select_tail_keeps_recent_turns_only():
    rest: list[dict] = []
    for i in range(6):
        rest.extend(_turn(f"user-{i}", f"reply-{i}" * 50))
    start = select_tail_start_index(
        rest,
        max_context_tokens=128_000,
        tail_turns=2,
        split_turn=False,
    )
    turns = group_messages_into_turns(rest)
    assert start >= turns[-2].start


@pytest.mark.unit
def test_split_turn_suffix_when_single_turn_huge():
    big = "x" * 8000
    rest = [
        {"role": "user", "content": "start"},
        {"role": "assistant", "content": big},
        {"role": "assistant", "content": "short tail reply"},
    ]
    turns = group_messages_into_turns(rest)
    assert len(turns) == 1
    start = select_tail_start_index(
        rest,
        max_context_tokens=12_000,
        tail_turns=1,
        split_turn=True,
    )
    assert start == 2
    assert rest[start]["content"] == "short tail reply"


@pytest.mark.unit
def test_split_head_tail_turns_produces_middle():
    messages = [{"role": "system", "content": "sys"}]
    for i in range(8):
        messages.extend(_turn(f"u{i}", f"a{i}" * 30))
    system, middle, head_tail = split_head_tail_turns(
        messages,
        max_context_tokens=128_000,
        head_count=1,
        min_tail_messages=2,
    )
    assert system and middle and head_tail
    assert len(middle) > 0


@pytest.mark.unit
def test_overflow_replay_appended_after_compress():
    messages = [{"role": "system", "content": "s"}]
    for _ in range(15):
        messages.append({"role": "user", "content": "block " * 80})
        messages.append({"role": "assistant", "content": "ok " * 80})
    messages.append({"role": "user", "content": "FINAL TASK: ship it"})

    with patch(
        "butler.core.context_compressor.auxiliary_complete",
        return_value="## Active Task\n- done",
    ):
        out, _, did = compress_messages(
            messages,
            max_tokens=5000,
            threshold_ratio=0.01,
            min_messages_to_compress=6,
            overflow_replay=True,
        )
    assert did
    assert any("FINAL TASK" in str(m.get("content", "")) for m in out)
    assert any("OVERFLOW REPLAY" in str(m.get("content", "")) for m in out)


@pytest.mark.unit
def test_find_overflow_replay_user_ignores_summary():
    msgs = [
        {"role": "user", "content": SUMMARY_PREFIX + "sum"},
        {"role": "user", "content": "real task"},
    ]
    replay = find_overflow_replay_user(msgs)
    assert replay is not None
    assert replay["content"] == "real task"


@pytest.mark.unit
def test_preserve_recent_budget_clamped():
    b = preserve_recent_token_budget(200_000)
    assert 2000 <= b <= 8000


@pytest.mark.unit
def test_diagnostics_strategy_turns_2():
    """8 turn 场景 → compaction_strategy='turns:2', tail_turns_kept=2."""
    rest: list[dict] = []
    for i in range(8):
        rest.append({"role": "user", "content": f"u-{i}"})
        rest.append({"role": "assistant", "content": f"a-{i}" * 50})
    diag: dict = {}
    start = select_tail_start_index(
        rest,
        max_context_tokens=128_000,
        tail_turns=2,
        split_turn=False,
        diagnostics=diag,
    )
    assert start > 0
    assert diag["compaction_strategy"] == "turns:2"
    assert diag["compaction_tail_turns_kept"] == 2
    assert diag["compaction_split_turn_applied"] is False
    assert isinstance(diag["compaction_preserved_recent_budget"], int)
    assert diag["compaction_tail_token_count"] > 0
    assert diag["compaction_tail_start_index"] == start


@pytest.mark.unit
def test_diagnostics_strategy_turns_2_split():
    """单个超大 turn 触发 mid-turn split → 'turns:1+split'."""
    big = "x" * 8000
    rest = [
        {"role": "user", "content": "start"},
        {"role": "assistant", "content": big},
        {"role": "assistant", "content": "short tail reply"},
    ]
    diag: dict = {}
    start = select_tail_start_index(
        rest,
        max_context_tokens=12_000,
        tail_turns=1,
        split_turn=True,
        diagnostics=diag,
    )
    assert start == 2
    assert diag["compaction_strategy"] == "turns:1+split"
    assert diag["compaction_split_turn_applied"] is True
    assert diag["compaction_tail_turns_kept"] == 1
    assert diag["compaction_tail_start_index"] == start


@pytest.mark.unit
def test_diagnostics_no_op_when_few_messages():
    """4 turn (≤ head + min_tail=2) → no_op, tail_start=0."""
    rest: list[dict] = []
    for i in range(4):
        rest.append({"role": "user", "content": f"u-{i}"})
        rest.append({"role": "assistant", "content": f"a-{i}"})
    diag: dict = {}
    # Note: select_tail_start_index doesn't know about head+min_tail, but with 4 turns
    # and tight budget the algorithm should produce a tail_start > 0; for "no_op" we
    # use the full-function path via split_head_tail_turns.
    system, middle, head_tail = split_head_tail_turns(
        rest,
        max_context_tokens=128_000,
        head_count=3,
        min_tail_messages=4,
        diagnostics=diag,
    )
    assert middle == []
    assert diag["compaction_strategy"] == "no_op"
    assert diag["compaction_tail_start_index"] == 0

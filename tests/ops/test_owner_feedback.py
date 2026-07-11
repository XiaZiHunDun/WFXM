"""Tests for Owner hard feedback (PROD-P0-01)."""

from __future__ import annotations

import json

import pytest

from butler.ops.owner_feedback import (
    is_owner_explicit_trigger,
    record_owner_hard_feedback,
)


@pytest.mark.unit
def test_is_owner_explicit_trigger():
    assert is_owner_explicit_trigger("owner_hard_feedback")
    assert is_owner_explicit_trigger("owner_reject_delegate")
    assert not is_owner_explicit_trigger("prod_delegate_verify_pass")


@pytest.mark.unit
def test_record_owner_hard_feedback(tmp_path, monkeypatch):
    # append_eval_feedback imports get_butler_home at module load;
    # monkeypatch the local binding in eval_actions.
    monkeypatch.setattr("butler.ops.eval_actions.get_butler_home", lambda: tmp_path)
    record_owner_hard_feedback(
        "委派结果不对，应该只读",
        session_key="wechat:u1:proj",
        platform="wechat",
        external_id="u1",
    )
    path = tmp_path / "audit" / "eval_feedback.jsonl"
    assert path.is_file()
    row = json.loads(path.read_text(encoding="utf-8").strip().splitlines()[-1])
    assert row["trigger"] == "owner_hard_feedback"
    assert row["source"] == "owner_explicit"
    assert row["evidence"] == "production"


@pytest.mark.unit
def test_record_owner_reject(tmp_path, monkeypatch):
    # append_eval_feedback imports get_butler_home at module load;
    # monkeypatch the local binding in eval_actions.
    monkeypatch.setattr("butler.ops.eval_actions.get_butler_home", lambda: tmp_path)
    record_owner_hard_feedback(
        "测试未绿",
        kind="reject",
        session_key="sk",
    )
    path = tmp_path / "audit" / "eval_feedback.jsonl"
    row = json.loads(path.read_text(encoding="utf-8").strip())
    assert row["trigger"] == "owner_reject_delegate"


@pytest.mark.unit
def test_record_owner_feedback_rejects_short():
    with pytest.raises(ValueError, match="太短"):
        record_owner_hard_feedback("x")

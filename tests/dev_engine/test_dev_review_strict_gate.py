"""Tests for dev review strict delegate gate."""

from __future__ import annotations

import pytest

from butler.dev_engine.b9_delegate_gate import apply_dev_review_strict_gate


@pytest.mark.unit
def test_strict_gate_blocks_when_review_failed(monkeypatch):
    monkeypatch.setenv("BUTLER_DEV_REVIEW_STRICT", "1")
    ok, issues = apply_dev_review_strict_gate(
        category="deep",
        role="dev",
        base_success=True,
        dev_engine={"review": {"passed": False, "findings_count": 2}},
    )
    assert ok is False
    assert any("DEV_REVIEW_STRICT_GATE" in i for i in issues)


@pytest.mark.unit
def test_strict_gate_off_by_default(monkeypatch):
    monkeypatch.delenv("BUTLER_DEV_REVIEW_STRICT", raising=False)
    ok, _ = apply_dev_review_strict_gate(
        category="deep",
        role="dev",
        base_success=True,
        dev_engine={"review": {"passed": False, "findings_count": 1}},
    )
    assert ok is True

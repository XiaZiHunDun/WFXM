"""Tests for delegate summary budget."""

import pytest

from butler.tools.delegate_summary_budget import (
    budget_delegate_payload,
    truncate_delegate_summary,
)


@pytest.mark.unit
def test_short_summary_unchanged():
    text = "done"
    assert truncate_delegate_summary(text, max_chars=100) == text


@pytest.mark.unit
def test_long_summary_truncated():
    text = "x" * 5000
    out = truncate_delegate_summary(text, max_chars=400)
    assert len(out) < len(text)
    assert "[truncated]" in out


@pytest.mark.unit
def test_budget_payload():
    payload = {"summary": "a" * 8000, "success": True}
    out = budget_delegate_payload(payload)
    assert out.get("summary_truncated") is True
    assert len(out["summary"]) < 8000

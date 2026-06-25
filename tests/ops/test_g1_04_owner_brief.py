"""Tests for G1-04 owner brief lines."""

from __future__ import annotations

import pytest

from butler.ops.boundary_observability import format_owner_g1_04_brief_lines


@pytest.mark.unit
def test_format_owner_g1_04_brief_lines():
    lines = format_owner_g1_04_brief_lines()
    text = "\n".join(lines)
    assert "OT2" in text
    assert "G1-04" in text
    assert "窗" in text

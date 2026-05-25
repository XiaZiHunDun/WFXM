"""Tests for harness diagnostics lines."""

from __future__ import annotations

from butler.ops.harness_diagnostics import format_harness_diagnostic_lines


def test_harness_diagnostics_includes_omo_lines():
    lines = format_harness_diagnostic_lines({"session_key": "test"}, session_key="test")
    joined = "\n".join(lines)
    assert "Tool-pair" in joined or "待办续跑" in joined

"""Ops snapshot for /诊断."""

from butler.ops.snapshot import collect_ops_snapshot, format_ops_diagnostic_lines


def test_collect_ops_snapshot_keys():
    snap = collect_ops_snapshot()
    assert "env" in snap
    assert "gateway_log" in snap
    assert "failure_streaks" in snap


def test_format_ops_diagnostic_lines():
    lines = format_ops_diagnostic_lines()
    assert any("运维快照" in ln for ln in lines)

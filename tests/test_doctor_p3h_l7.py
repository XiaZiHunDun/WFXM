"""Doctor diagnostics for P3-H memory recall and L7 approval storage."""

from __future__ import annotations

from butler.ops.approval_diagnostics_ops import format_approval_storage_doctor_lines
from butler.ops.memory_recall_diagnostics_ops import format_memory_recall_doctor_lines


def test_memory_recall_doctor_lines_unified_on(monkeypatch):
    monkeypatch.setenv("BUTLER_MEMORY_UNIFIED_RECALL", "1")
    monkeypatch.setenv("BUTLER_MEMORY_OBSERVATION_RECALL", "1")
    monkeypatch.setenv("BUTLER_MEMORY_OBSERVER_QUEUE", "1")
    monkeypatch.setenv("BUTLER_TRANSCRIPT_FTS", "1")
    lines = format_memory_recall_doctor_lines()
    text = "\n".join(lines)
    assert "统一 hybrid 召回: 开" in text
    assert "observation 辅助召回: 开" in text
    assert "Observation 队列: 开" in text
    assert "gateway lead 剖面 P3-H: ✓" in text


def test_approval_storage_doctor_lines(tmp_butler_home):
    lines = format_approval_storage_doctor_lines(tmp_butler_home)
    text = "\n".join(lines)
    assert "ApprovalStore: ✓" in text
    assert "WorkflowGateStore: ✓" in text
    assert "approvals.json" in text
    assert "遗留 exec_approvals" in text

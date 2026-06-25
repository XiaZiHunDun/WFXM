"""Tests for compaction evidence extraction."""

from __future__ import annotations

import pytest

from butler.core.evidence_extract import (
    append_evidence_to_summary,
    extract_compact_evidence,
)


@pytest.mark.unit
def test_extract_compact_evidence_prefers_tool_and_paths():
    middle = [
        {"role": "user", "content": "请修复 tests/foo.py 里的 pytest 失败"},
        {
            "role": "tool",
            "content": "AssertionError: expected 1 got 2 in tests/foo.py",
        },
    ]
    lines = extract_compact_evidence(middle, max_lines=3)
    assert lines
    assert any("foo.py" in ln for ln in lines)


@pytest.mark.unit
def test_append_evidence_to_summary_prefixes_block():
    middle = [{"role": "tool", "content": "verify failed: patch rejected in butler/core/agent_loop.py"}]
    out = append_evidence_to_summary("summary body", middle, diagnostics={})
    assert "Compact evidence" in out
    assert "summary body" in out

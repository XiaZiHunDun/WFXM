"""Tests for tool_batch auxiliary state module."""

from __future__ import annotations

from butler.core.tool_batch_state import (
    clear_pre_edit_snapshots,
    pop_pre_edit_snapshot,
    pre_edit_snapshot_count,
    store_pre_edit_snapshot,
)


def test_store_pop_clear():
    clear_pre_edit_snapshots()
    store_pre_edit_snapshot("/tmp/a.py", "content")
    assert pre_edit_snapshot_count() == 1
    assert pop_pre_edit_snapshot("/tmp/a.py") == "content"
    assert pop_pre_edit_snapshot("/tmp/a.py") is None
    clear_pre_edit_snapshots()
    assert pre_edit_snapshot_count() == 0

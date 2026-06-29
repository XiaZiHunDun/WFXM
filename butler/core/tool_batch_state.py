"""Auxiliary mutable state for tool_batch (pre-edit file snapshots)."""

from __future__ import annotations

_pre_edit_snapshots: dict[str, str] = {}


def store_pre_edit_snapshot(resolved_path: str, content: str) -> None:
    _pre_edit_snapshots[str(resolved_path)] = content


def pop_pre_edit_snapshot(resolved_path: str) -> str | None:
    return _pre_edit_snapshots.pop(str(resolved_path), None)


def clear_pre_edit_snapshots() -> None:
    _pre_edit_snapshots.clear()


def pre_edit_snapshot_count() -> int:
    return len(_pre_edit_snapshots)


__all__ = [
    "clear_pre_edit_snapshots",
    "pop_pre_edit_snapshot",
    "pre_edit_snapshot_count",
    "store_pre_edit_snapshot",
]

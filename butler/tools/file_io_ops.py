"""File I/O tool best-effort helpers (P0-A)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from butler.core.best_effort import safe_best_effort


def record_read_path_safe(path: Path, *, workspace_root: Path | None) -> None:
    def _run() -> None:
        from butler.core.instruction_walkup import record_read_path

        record_read_path(path, workspace_root=workspace_root)

    safe_best_effort(_run, label="file_io.record_read_path", default=None)


def record_edit_path_safe(path: Path | None) -> None:
    if path is None:
        return

    def _run() -> None:
        from butler.core.read_state import record_edit_path

        record_edit_path(path)

    safe_best_effort(_run, label="file_io.record_edit_path", default=None)


def maybe_format_after_edit_safe(path: Path) -> dict[str, Any] | None:
    def _run() -> dict[str, Any] | None:
        from butler.core.post_edit_format import maybe_format_after_edit

        fmt = maybe_format_after_edit(path)
        return fmt if isinstance(fmt, dict) else None

    return safe_best_effort(_run, label="file_io.post_edit_format", default=None)


def verify_hashline_anchors_safe(path: Path, old_string: str) -> dict[str, Any] | None:
    def _run() -> dict[str, Any] | None:
        from butler.core.hashline import extract_anchors_from_old_string, verify_line_anchors

        anchors = extract_anchors_from_old_string(old_string)
        mismatch = verify_line_anchors(path, anchors)
        return mismatch if isinstance(mismatch, dict) else None

    return safe_best_effort(_run, label="file_io.hashline_anchors", default=None)


def tool_json_loud(run: Callable[[], str]) -> str:
    try:
        return run()
    except Exception as exc:
        return json.dumps({"error": str(exc)})

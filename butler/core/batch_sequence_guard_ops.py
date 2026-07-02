"""Batch sequence guard best-effort helpers (P0-A)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from butler.core.best_effort import safe_best_effort


def normalize_batch_path_safe(path: str) -> str:
    def _run() -> str:
        return str(Path(path).expanduser().resolve())

    result = safe_best_effort(_run, label="batch_sequence_guard.normalize_path", default=path)
    return result if isinstance(result, str) else str(path or "").strip()


def parse_batch_tool_args_safe(tc: Any) -> dict[str, Any]:
    def _run() -> dict[str, Any]:
        if hasattr(tc, "args_dict"):
            return tc.args_dict()
        if isinstance(tc, dict):
            import json as _json

            raw = (tc.get("function") or {}).get("arguments", "{}")
            return _json.loads(raw) if isinstance(raw, str) else dict(raw or {})
        return {}

    result = safe_best_effort(_run, label="batch_sequence_guard.tool_args", default={})
    return result if isinstance(result, dict) else {}


def record_edit_paths_safe(tool_name: str, args: dict[str, Any] | None) -> None:
    def _run() -> None:
        from butler.core.batch_sequence_guard import extract_tool_scope_paths
        from butler.core.read_state import record_edit_path

        for path in extract_tool_scope_paths(tool_name, args):
            record_edit_path(path)

    safe_best_effort(_run, label="batch_sequence_guard.record_edit", default=None)

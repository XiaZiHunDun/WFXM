"""Turn summary tool-action load best-effort helpers (P0-A)."""

from __future__ import annotations

from typing import Any

from butler.core.best_effort import safe_best_effort


def load_current_turn_tool_actions_safe(
    session_key: str,
    *,
    max_lines: int = 500,
) -> list[dict[str, Any]]:
    def _run() -> list[dict[str, Any]]:
        from butler.core.session_epoch import load_current_turn_tool_actions

        rows = load_current_turn_tool_actions(session_key, max_lines=max_lines)
        if not isinstance(rows, list):
            raise ValueError("turn tool actions must be a list")
        return rows

    result = safe_best_effort(
        _run,
        label="turn_summary_line.tool_actions",
        default=[],
    )
    return list(result) if isinstance(result, list) else []

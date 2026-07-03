"""Session tool index transcript load best-effort helpers (P0-A)."""

from __future__ import annotations

from typing import Any

from butler.core.best_effort import safe_best_effort


def load_epoch_transcript_rows_safe(
    session_key: str,
    *,
    max_lines: int = 500,
) -> list[dict[str, Any]] | None:
    """Return transcript rows, or ``None`` when the load path failed."""

    def _run() -> list[dict[str, Any]]:
        from butler.core.session_epoch import load_epoch_transcript_rows

        rows = load_epoch_transcript_rows(session_key, max_lines=max_lines)
        if not isinstance(rows, list):
            raise ValueError("epoch transcript rows must be a list")
        return rows

    result = safe_best_effort(
        _run,
        label="session_tool_index.transcript_rows",
        default=None,
    )
    return list(result) if isinstance(result, list) else None

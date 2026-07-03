"""Session epoch transcript best-effort helpers (P0-A)."""

from __future__ import annotations

from typing import Any

from butler.core.best_effort import safe_best_effort


def load_transcript_rows_safe(
    session_key: str,
    *,
    max_lines: int | None = None,
) -> list[dict[str, Any]]:
    def _run() -> list[dict[str, Any]]:
        from butler.core.transcript_export import load_transcript_rows

        rows = load_transcript_rows(session_key, max_lines=max_lines)
        if not isinstance(rows, list):
            raise ValueError("transcript rows must be a list")
        return rows

    result = safe_best_effort(
        _run,
        label="session_epoch.transcript_rows",
        default=[],
    )
    return list(result) if isinstance(result, list) else []

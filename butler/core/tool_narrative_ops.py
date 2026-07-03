"""Tool narrative transcript load best-effort helpers (P0-A)."""

from __future__ import annotations

from typing import Any

from butler.core.session_tool_index_ops import load_epoch_transcript_rows_safe


def load_transcript_rows_for_narrative_safe(
    session_key: str,
    *,
    max_lines: int = 200,
) -> list[dict[str, Any]] | None:
    return load_epoch_transcript_rows_safe(session_key, max_lines=max_lines)

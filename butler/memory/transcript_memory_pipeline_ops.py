"""Transcript memory facade load best-effort helpers (P0-A)."""

from __future__ import annotations

from typing import Any

from butler.core.best_effort import safe_best_effort


def load_transcript_memory_facades_safe(
    project_name: str = "",
) -> tuple[Any | None, Any | None]:
    def _run() -> tuple[Any, Any]:
        from butler.memory.facade import get_butler_memory, get_project_memory

        return get_butler_memory(), get_project_memory(project_name or None)

    result = safe_best_effort(
        _run,
        label="transcript_memory_pipeline.facade",
        default=(None, None),
    )
    if isinstance(result, tuple) and len(result) == 2:
        return result[0], result[1]
    return None, None

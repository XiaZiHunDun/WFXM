"""Search hit enrichment best-effort helpers (P0-A)."""

from __future__ import annotations

from typing import Any

from butler.core.best_effort import safe_best_effort


def parse_chunk_metadata_safe(content: str) -> dict[str, Any]:
    def _run() -> dict[str, Any]:
        from butler.memory.chunking import parse_chunk_metadata

        meta = parse_chunk_metadata(content)
        return meta if isinstance(meta, dict) else {}

    result = safe_best_effort(
        _run,
        label="search_result.chunk_metadata",
        default={},
    )
    return result if isinstance(result, dict) else {}

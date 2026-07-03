"""Markdown chunk indexing best-effort helpers (P0-A)."""

from __future__ import annotations

import logging
from typing import Any

from butler.core.best_effort import safe_best_effort

logger = logging.getLogger(__name__)


def index_markdown_chunk_safe(
    semantic: Any,
    chunk: Any,
    *,
    project_name: str,
    payload: str,
) -> bool:
    def _run() -> bool:
        from butler.memory.semantic_index import SOURCE_PROJECT, index_triplets_for_content

        semantic.upsert(
            source=SOURCE_PROJECT,
            source_id=chunk.source_id,
            content=payload,
            project=project_name,
            category="project_doc",
        )
        index_triplets_for_content(
            semantic,
            chunk.content,
            project=project_name,
            source=SOURCE_PROJECT,
            source_ref=chunk.parent_doc_id,
        )
        return True

    result = safe_best_effort(
        _run,
        label="chunking.markdown_index",
        default=False,
    )
    if result is False:
        logger.warning("Markdown chunk index failed %s", getattr(chunk, "source_id", ""))
    return bool(result)

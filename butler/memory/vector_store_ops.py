"""Chroma / fallback vector store error handling (P0-A)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def chroma_query(collection: Any, kwargs: dict[str, Any]) -> dict[str, Any] | None:
    try:
        return collection.query(**kwargs)
    except Exception as exc:
        logger.warning("ChromaDB query failed: %s", exc)
        return None


def chroma_delete(collection: Any, doc_id: str) -> bool:
    try:
        collection.delete(ids=[doc_id])
        return True
    except Exception:
        return False


def load_fallback_docs(persist_path: Path) -> list[dict[str, Any]]:
    if not persist_path.is_file():
        return []
    try:
        rows: list[dict[str, Any]] = []
        for line in persist_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            entry = json.loads(line)
            if isinstance(entry, dict) and entry.get("id"):
                rows.append(entry)
        return rows
    except Exception as exc:
        logger.debug("Failed to load fallback vector store: %s", exc)
        return []


def create_chroma_store(factory: Any) -> Any:
    try:
        return factory()
    except ImportError:
        raise
    except Exception as exc:
        logger.warning("ChromaDB init failed (%s); using fallback", exc)
        return None


def init_vector_store(
    *,
    collection: str,
    chroma_factory: Any,
    fallback_factory: Any,
    on_chroma: Any,
    on_import_error: Any,
    on_fallback: Any,
) -> Any:
    try:
        chroma = create_chroma_store(chroma_factory)
        if chroma is not None:
            on_chroma(collection)
            return chroma
        store = fallback_factory()
        on_fallback()
        return store
    except ImportError:
        on_import_error()
        return fallback_factory()

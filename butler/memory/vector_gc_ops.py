"""Vector GC best-effort helpers (P0-A)."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def close_butler_memory_safe(bm: Any) -> None:
    try:
        bm.close()
    except Exception:
        pass


def delete_orphan_vector_safe(semantic: Any, source: str, source_id: str) -> bool:
    try:
        semantic.delete(source, source_id)
        return True
    except Exception as exc:
        logger.debug("GC orphan delete skipped for %s: %s", source_id, exc)
        return False


def delete_conversation_vectors_safe(semantic: Any, category: str) -> int | None:
    try:
        return int(semantic.delete_by_category(category))
    except Exception as exc:
        logger.warning("GC conversation vector purge failed: %s", exc)
        return None

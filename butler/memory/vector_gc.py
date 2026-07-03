"""Garbage-collect orphan experience vectors (MT7 derivative index hygiene)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from butler.memory.butler_memory import ButlerMemory
from butler.memory.semantic_health import drift_from_butler_memory
from butler.memory.semantic_index import SOURCE_EXPERIENCE

logger = logging.getLogger(__name__)

_CONVERSATION = "conversation"


def _valid_experience_ids(experience_store: Any) -> set[str]:
    with experience_store._lock:
        conn = experience_store._conn
        rows = conn.execute("SELECT id FROM experiences").fetchall()
    return {str(int(r[0])) for r in rows}


def _orphan_experience_source_ids(semantic: Any, valid_ids: set[str]) -> list[str]:
    conn = semantic._conn
    rows = conn.execute(
        "SELECT source_id FROM memory_vectors WHERE source = ?",
        (SOURCE_EXPERIENCE,),
    ).fetchall()
    return [str(r[0]) for r in rows if str(r[0]) not in valid_ids]


def _count_conversation_vectors(semantic: Any) -> int:
    conn = semantic._conn
    row = conn.execute(
        "SELECT COUNT(*) FROM memory_vectors WHERE category = ?",
        (_CONVERSATION,),
    ).fetchone()
    return int(row[0] if row else 0)


def run_memory_gc(
    butler_home: Path,
    *,
    tenant_id: str = "default",
    apply: bool = False,
) -> dict[str, Any]:
    """Report or remove experience-vector orphans and stale conversation vectors."""
    bm = ButlerMemory(Path(butler_home).expanduser().resolve(), tenant_id=tenant_id)
    sem = bm.semantic
    from butler.memory.vector_gc_ops import (
        close_butler_memory_safe,
        delete_conversation_vectors_safe,
        delete_orphan_vector_safe,
    )

    if sem is None:
        close_butler_memory_safe(bm)
        return {
            "ok": False,
            "error": "BUTLER_SEMANTIC_MEMORY is not enabled",
            "dry_run": not apply,
        }

    valid_ids = _valid_experience_ids(bm.experience)
    orphan_ids = _orphan_experience_source_ids(sem, valid_ids)
    conv_vectors = _count_conversation_vectors(sem)
    drift = drift_from_butler_memory(bm)

    result: dict[str, Any] = {
        "ok": True,
        "dry_run": not apply,
        "tenant_id": bm.tenant_id,
        "orphan_experience_vectors": len(orphan_ids),
        "conversation_vectors": conv_vectors,
        "deleted_orphan_vectors": 0,
        "deleted_conversation_vectors": 0,
        "sample_orphan_ids": orphan_ids[:12],
        "experience_rows": len(valid_ids),
        "semantic_index_gap": drift.get("semantic_index_gap"),
        "semantic_index_stale": drift.get("semantic_index_stale"),
    }

    if apply:
        deleted_orphans = 0
        for sid in orphan_ids:
            if delete_orphan_vector_safe(sem, SOURCE_EXPERIENCE, sid):
                deleted_orphans += 1
        result["deleted_orphan_vectors"] = deleted_orphans
        if conv_vectors:
            deleted_conv = delete_conversation_vectors_safe(sem, _CONVERSATION)
            if deleted_conv is not None:
                result["deleted_conversation_vectors"] = deleted_conv
        drift_after = drift_from_butler_memory(bm)
        result["semantic_index_gap_after"] = drift_after.get("semantic_index_gap")
        result["semantic_index_stale_after"] = drift_after.get("semantic_index_stale")

    close_butler_memory_safe(bm)
    return result

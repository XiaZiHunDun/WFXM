"""Best-effort helpers for ``ButlerMemory`` lifecycle (P0-A)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from butler.core.best_effort import safe_best_effort


def close_sqlite_connection(conn: Any) -> None:
    safe_best_effort(
        lambda: conn.close(),
        label="butler_memory.close_connection",
        default=None,
    )


def seed_bundled_tenant_skills(butler_home: Any, tenant_id: str) -> None:
    def _run() -> None:
        from butler.skills.seed_bundled import ensure_bundled_tenant_skills

        ensure_bundled_tenant_skills(butler_home, tenant_id)

    safe_best_effort(_run, label="butler_memory.bundled_skills_seed", default=None)


def open_semantic_index(mem_dir: Path) -> Any | None:
    def _run() -> Any | None:
        from butler.memory.semantic_config import semantic_memory_enabled
        from butler.memory.semantic_index import SemanticMemoryIndex

        if not semantic_memory_enabled():
            return None
        return SemanticMemoryIndex(mem_dir / "memory_vectors.db")

    return safe_best_effort(
        _run,
        label="butler_memory.semantic_index_init",
        default=None,
    )


def delete_experience_vector(sem: Any, row_id: int) -> bool:
    def _run() -> bool:
        from butler.memory.semantic_index import SOURCE_EXPERIENCE

        sem.delete(SOURCE_EXPERIENCE, str(row_id))
        return True

    return safe_best_effort(
        _run,
        label="butler_memory.vector_delete_experience",
        default=False,
    ) is True


def close_memory_store(store: Any) -> None:
    if store is None:
        return
    safe_best_effort(
        lambda: store.close(),
        label="butler_memory.close_store",
        default=None,
    )


__all__ = [
    "close_memory_store",
    "close_sqlite_connection",
    "delete_experience_vector",
    "open_semantic_index",
    "seed_bundled_tenant_skills",
]

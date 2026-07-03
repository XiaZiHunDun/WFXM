"""Owner experience seed best-effort helpers (P0-A)."""

from __future__ import annotations

from typing import Any

from butler.core.best_effort import safe_best_effort


def delete_experience_vector_safe(sem: Any, row_id: int) -> bool:
    def _run() -> bool:
        from butler.memory.semantic_index import SOURCE_EXPERIENCE

        sem.delete(SOURCE_EXPERIENCE, str(row_id))
        return True

    result = safe_best_effort(
        _run,
        label="owner_experience_seed.vector_delete",
        default=False,
    )
    return bool(result)


def close_butler_memory_safe(bm: Any) -> None:
    def _run() -> None:
        bm.close()

    safe_best_effort(_run, label="owner_experience_seed.memory_close", default=None)

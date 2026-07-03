"""Project memory best-effort helpers (P0-A)."""

from __future__ import annotations

from pathlib import Path

from butler.core.best_effort import safe_best_effort


def looks_correction_intent_safe(content: str) -> bool:
    def _run() -> bool:
        from butler.core.correction_intent import is_correction_intent

        return bool(is_correction_intent(content))

    result = safe_best_effort(
        _run,
        label="project_memory.correction_intent",
        default=False,
    )
    return bool(result)


def sync_facts_to_knowledge_db_safe(path: Path) -> None:
    def _run() -> None:
        from butler.memory.knowledge_db import sync_facts_json_to_knowledge_db

        sync_facts_json_to_knowledge_db(path)

    safe_best_effort(_run, label="project_memory.sync_knowledge_db", default=None)

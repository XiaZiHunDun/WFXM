"""B9 live tuning best-effort helpers (P0-A)."""

from __future__ import annotations

from butler.core.best_effort import safe_best_effort


def append_curriculum_block_safe(lines: list[str], task_id: str) -> None:
    def _run() -> None:
        from butler.dev_engine.b9_oracle_curriculum import format_curriculum_block

        block = format_curriculum_block(task_id, max_steps=4)
        if block:
            lines.append(block)

    safe_best_effort(_run, label="b9_live_tuning.curriculum_block", default=None)


def append_b9_lessons_block_safe(lines: list[str], task_id: str) -> None:
    def _run() -> None:
        from butler.ops.b9_lessons import format_b9_lessons_block

        lessons = format_b9_lessons_block(task_id, limit=2)
        if lessons:
            lines.append(lessons)

    safe_best_effort(_run, label="b9_live_tuning.lessons_block", default=None)


def append_b9_learning_blocks_safe(lines: list[str], task_id: str) -> None:
    append_curriculum_block_safe(lines, task_id)
    append_b9_lessons_block_safe(lines, task_id)

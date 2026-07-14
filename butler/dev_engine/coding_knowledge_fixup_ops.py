"""Coding knowledge fixup best-effort helpers (P0-A)."""

from __future__ import annotations

from typing import Any, cast

from butler.core.best_effort import safe_best_effort


def effective_coding_knowledge_strict_safe(*, default: bool = False) -> bool:
    def _run() -> bool:
        from butler.ops.eval_config_overrides import effective_coding_knowledge_strict

        return bool(effective_coding_knowledge_strict(default))

    result = safe_best_effort(
        _run,
        label="coding_knowledge_fixup.strict_experience",
        default=default,
    )
    return bool(result)


def record_fix_reactivation_selection_safe(
    *,
    session_key: str,
    task_preview: str,
    experience_id: str,
    experience_mode: str,
    keywords: list[str],
    inferred_task_id: str,
) -> None:
    def _run() -> None:
        from butler.ops.experience_selection_telemetry import record_experience_selection

        record_experience_selection(
            session_key=session_key,
            task_preview=task_preview[:300],
            experience_id=experience_id,
            experience_mode=experience_mode,
            keywords=keywords[:24],
            role="dev",
            inferred_task_id=inferred_task_id,
            selection_phase="fix_reactivation",
        )

    safe_best_effort(_run, label="coding_knowledge_fixup.selection_telemetry", default=None)


def reactivate_coding_knowledge_core_safe(state: Any, keywords: list[str]) -> dict[str, Any] | None:
    def _run() -> dict[str, Any]:
        from butler.config import get_butler_home
        from butler.dev_engine.coding_knowledge import (
            TheoremLibrary,
            process_task,
        )
        from butler.memory.memory_scope import load_delegate_experience_library

        project_id = str(getattr(state, "_delegate_project_id", "") or "")
        stack_tags = getattr(state, "_delegate_stack_tags", None) or frozenset()
        inferred_task_id = str(getattr(state, "_inferred_task_id", "") or "")
        project = getattr(state, "_delegate_project", None)

        tlib = TheoremLibrary()
        xlib = load_delegate_experience_library(
            butler_home=get_butler_home(),
            project=project,
            theorem_lib=tlib,
        )
        strict = effective_coding_knowledge_strict_safe(default=True)

        prev_id = ""
        ck = getattr(state, "coding_knowledge", None)
        if ck is not None:
            prev_id = str(getattr(ck, "experience_id", "") or "")

        ctx = process_task(
            keywords,
            tlib,
            xlib,
            strict_experience=strict,
            project_id=project_id,
            stack_tags=stack_tags,
            inferred_task_id=inferred_task_id,
        )

        if ck is not None:
            ck.mode = ctx.mode
            ck.activated_theorem_ids = sorted(ctx.activated_theorems.keys())
            ck.activated_elements = [e.value for e in ctx.activated_elements]
            if ctx.selected_experience is not None:
                ck.experience_id = ctx.selected_experience.id
                ck.experience_title = ctx.selected_experience.title
            else:
                ck.experience_id = ""
                ck.experience_title = ""

        state._coding_knowledge_ctx = ctx
        state._coding_knowledge_theorems = ctx.activated_theorems
        count = int(getattr(state, "_coding_knowledge_reactivation_count", 0) or 0) + 1
        state._coding_knowledge_reactivation_count = count

        new_id = ctx.selected_experience.id if ctx.selected_experience else ""
        if new_id and new_id != prev_id:
            record_fix_reactivation_selection_safe(
                session_key=str(getattr(state, "_delegate_session_key", "") or ""),
                task_preview=str(getattr(state, "task_description", "") or ""),
                experience_id=new_id,
                experience_mode=ctx.mode,
                keywords=keywords,
                inferred_task_id=inferred_task_id,
            )

        return {
            "reactivated": True,
            "experience_id": new_id,
            "experience_mode": ctx.mode,
            "keywords": keywords[:12],
            "reactivation_count": count,
            "experience_changed": bool(new_id and new_id != prev_id),
        }

    result = safe_best_effort(
        _run,
        label="coding_knowledge_fixup.reactivate",
        default=None,
    )
    return result if isinstance(result, dict) else None

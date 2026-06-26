"""Dev delegate session bootstrap (extracted from ``delegate_phases`` ENG-2)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from butler.tools.delegate_phases import DelegateRunState

logger = logging.getLogger(__name__)


def init_dev_engine_state_for_delegate(state: DelegateRunState) -> None:
    """Initialize DevState + DevEnginePlugin for dev delegates (4g / D3-7)."""
    norm = state.role.replace("_agent", "").strip().lower()
    if norm != "dev":
        return
    try:
        from butler.dev_engine.dev_tools import dev_engine_enabled
        from butler.dev_engine.dev_loop import create_dev_state

        if not dev_engine_enabled():
            return
        sk = state.child_session_key or state.session_key or "_default"
        ds = create_dev_state(task_description=state.task)
        ds._delegate_category = str(
            state.category_meta.get("category") or state.category or ""
        )

        _activate_coding_knowledge(state, ds, sk)
        _register_dev_state_and_plugin(state, ds, sk)
    except Exception as exc:  # noqa: BLE001 — best-effort init
        logger.debug("DevState initialization skipped: %s", exc)


def _activate_coding_knowledge(state: DelegateRunState, ds: object, sk: str) -> None:
    try:
        from butler.config import get_butler_home as _get_butler_home
        from butler.dev_engine.coding_knowledge import TheoremLibrary, process_task
        from butler.dev_engine.dev_state import CodingKnowledgeSummary
        from butler.dev_engine.prod_delegate_bridge import (
            infer_b9_task_id,
            production_delegate_keywords,
        )
        from butler.memory.memory_scope import (
            delegate_project_id,
            load_delegate_experience_library,
            stack_tags_for_project,
        )

        keywords = production_delegate_keywords(
            state.task,
            state.context,
            category=state.category,
            category_meta=state.category_meta,
        )
        inferred_task_id = ""
        try:
            inferred_task_id = infer_b9_task_id(
                state.task,
                state.context,
                category=state.category,
                category_meta=state.category_meta,
            )
        except Exception:
            inferred_task_id = ""
        tlib = TheoremLibrary()
        xlib = load_delegate_experience_library(
            butler_home=_get_butler_home(),
            project=state.project,
            theorem_lib=tlib,
        )
        project_id = delegate_project_id(state.project)
        stack_tags = stack_tags_for_project(state.project)
        try:
            from butler.ops.eval_config_overrides import effective_coding_knowledge_strict

            strict = effective_coding_knowledge_strict(True)
        except Exception:
            strict = True
        ctx = process_task(
            keywords,
            tlib,
            xlib,
            strict_experience=strict,
            project_id=project_id,
            stack_tags=stack_tags,
            inferred_task_id=inferred_task_id,
        )
        if ctx.selected_experience is not None:
            try:
                from butler.ops.experience_selection_telemetry import (
                    record_experience_selection,
                )

                record_experience_selection(
                    session_key=sk,
                    task_preview=state.task,
                    experience_id=ctx.selected_experience.id,
                    experience_mode=ctx.mode,
                    keywords=keywords[:24],
                    role=state.role,
                    inferred_task_id=inferred_task_id,
                )
            except Exception:
                pass
        ds.coding_knowledge = CodingKnowledgeSummary(
            mode=ctx.mode,
            activated_theorem_ids=sorted(ctx.activated_theorems.keys()),
            activated_elements=[e.value for e in ctx.activated_elements],
            experience_id=(
                ctx.selected_experience.id if ctx.selected_experience else ""
            ),
            experience_title=(
                ctx.selected_experience.title if ctx.selected_experience else ""
            ),
        )
        ds._coding_knowledge_theorems = ctx.activated_theorems
        ds._coding_knowledge_ctx = ctx
        ds._delegate_keywords = keywords
        ds._delegate_project_id = project_id
        ds._delegate_stack_tags = stack_tags
        ds._inferred_task_id = inferred_task_id
        ds._delegate_project = state.project
        ds._delegate_session_key = sk
    except Exception as exc:
        logger.debug("coding knowledge activation skipped: %s", exc)


def _register_dev_state_and_plugin(state: DelegateRunState, ds: object, sk: str) -> None:
    from butler.dev_engine.dev_tools import _active_states

    _active_states[sk] = ds

    if state.agent is not None:
        try:
            from butler.dev_engine.loop_plugin import create_dev_engine_plugin

            plugin = create_dev_engine_plugin(session_key=sk)
            plugins = getattr(state.agent, "_plugins", None)
            if plugins is not None:
                plugins.plugins.append(plugin)
                before_hook = getattr(plugin, "before_model", None)
                if callable(before_hook):
                    plugins._before_llm_hooks.append(before_hook)
                after_hook = getattr(plugin, "after_tools", None)
                if callable(after_hook):
                    plugins._after_tools_hooks.append(after_hook)
        except Exception as exc:
            logger.debug("DevEnginePlugin registration skipped: %s", exc)

    logger.debug("DevState initialized for session %s", sk)


__all__ = ["init_dev_engine_state_for_delegate"]

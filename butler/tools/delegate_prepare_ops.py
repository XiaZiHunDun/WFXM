"""Delegate prepare best-effort helpers (P0-A)."""

from __future__ import annotations

from butler.core.best_effort import safe_best_effort
from butler.tools.delegate_run_state import DelegateRunState


def infer_delegate_category_safe(task: str) -> str:
    def _run() -> str:
        from butler.core.intent_keywords import category_from_intent

        return str(category_from_intent(task) or "")

    result = safe_best_effort(
        _run,
        label="delegate_prepare.infer_category",
        default="",
    )
    return str(result or "")


def inject_verify_checklist_safe(state: DelegateRunState) -> None:
    def _run() -> None:
        from butler.agent_profiles import DELEGATE_VERIFY_CHECKLIST

        text = DELEGATE_VERIFY_CHECKLIST.strip()
        if text:
            state.context = (state.context or "").rstrip() + "\n\n" + text

    safe_best_effort(_run, label="delegate_prepare.verify_checklist", default=None)


def inject_production_playbook_bridge_safe(state: DelegateRunState) -> None:
    def _run() -> None:
        from butler.dev_engine.prod_delegate_bridge import enrich_delegate_context_for_production

        state.context = enrich_delegate_context_for_production(
            state.context,
            task=state.task,
            category=state.category,
            category_meta=state.category_meta,
        )

    safe_best_effort(_run, label="delegate_prepare.prod_playbook", default=None)

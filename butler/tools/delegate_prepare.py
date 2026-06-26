"""Delegate phase 1 — task enrichment and depth guard (ENG-2)."""

from __future__ import annotations

import json
import logging

from butler.tools.delegate_run_state import DelegateRunState

logger = logging.getLogger(__name__)


def infer_delegate_category(task: str) -> str:
    """Best-effort category inference from task intent (1a)."""
    try:
        from butler.core.intent_keywords import category_from_intent

        return str(category_from_intent(task) or "")
    except Exception as exc:  # noqa: BLE001 — best-effort inference
        logger.debug("intent category inference skipped: %s", exc)
        return ""


def apply_category_resolver(state: DelegateRunState) -> None:
    """Apply category resolver — rewrites role/task/context (1b)."""
    if not str(state.category or "").strip():
        return
    from butler.delegate.category_resolver import apply_category_to_delegate

    new_role, new_task, new_context, category_meta = apply_category_to_delegate(
        category=str(state.category).strip(),
        role=state.role,
        task=state.task,
        context=state.context,
    )
    state.role = new_role
    state.task = new_task
    state.context = new_context
    state.category_meta = category_meta


def build_handoff_block_text(cat_name: str, role: str, task: str) -> str:
    """Render the handoff markdown for a category (1c, pure)."""
    from butler.core.handoff import default_visual_acceptance, render_handoff_block

    if cat_name == "ui-build":
        acceptance = default_visual_acceptance()
        evidence_required = ["read_file DESIGN.md", "read_file 改动文件"]
    else:
        acceptance = [
            "任务描述中的目标已达成",
            "关键改动有 read_file 或测试证据",
        ]
        evidence_required = ["read_file 或 pytest"]
    return render_handoff_block(
        from_role="butler",
        to_role=str(role or "dev"),
        task=task,
        acceptance=acceptance,
        evidence_required=evidence_required,
    )


def inject_handoff_block(state: DelegateRunState) -> None:
    """Inject handoff markdown for nexus / ui-build / first-time (1c)."""
    from butler.core.handoff import merge_handoff_into_context

    cat_name = str(
        state.category or state.category_meta.get("category") or ""
    ).strip().lower()
    needs_handoff = (
        cat_name.startswith("nexus")
        or cat_name == "ui-build"
        or "## Handoff" not in str(state.context or "")
    )
    if not needs_handoff:
        return
    handoff = build_handoff_block_text(cat_name, state.role, state.task)
    state.context = merge_handoff_into_context(state.context, handoff)


def inject_verify_checklist(state: DelegateRunState) -> None:
    """Append the delegate verify checklist to context (1d, best-effort)."""
    try:
        from butler.agent_profiles import DELEGATE_VERIFY_CHECKLIST

        text = DELEGATE_VERIFY_CHECKLIST.strip()
        if text:
            state.context = (state.context or "").rstrip() + "\n\n" + text
    except Exception as exc:  # noqa: BLE001 — best-effort injection
        logger.debug("delegate verify checklist skipped: %s", exc)


def check_delegate_depth(state: DelegateRunState) -> None:
    """Set ``early_return`` when ``depth >= MAX_DELEGATE_DEPTH`` (1f)."""
    from butler.delegate.policy import MAX_DELEGATE_DEPTH

    if state.depth >= MAX_DELEGATE_DEPTH:
        state.early_return = json.dumps(
            {"error": f"Maximum delegation depth ({MAX_DELEGATE_DEPTH}) exceeded"}
        )


def inject_production_playbook_bridge(state: DelegateRunState) -> None:
    """Prepend B9 seed playbooks for production-shaped dev delegates (P0 bridge)."""
    try:
        from butler.dev_engine.prod_delegate_bridge import enrich_delegate_context_for_production

        state.context = enrich_delegate_context_for_production(
            state.context,
            task=state.task,
            category=state.category,
            category_meta=state.category_meta,
        )
    except Exception as exc:  # noqa: BLE001 — best-effort enrichment
        logger.debug("production playbook bridge skipped: %s", exc)


def prepare_delegate_task(state: DelegateRunState) -> None:
    """Phase 1: enrich (role, task, context, category) and check depth."""
    from butler.tools.delegate_role_guard import (
        apply_user_role_override,
        block_lead_readonly_delegate,
        user_explicit_delegate_role,
        _explicit_role_from_state,
        _turn_user_text,
    )

    blocked = block_lead_readonly_delegate(depth=state.depth)
    if blocked:
        state.early_return = blocked
        return

    pinned = user_explicit_delegate_role(_turn_user_text()) or _explicit_role_from_state(state)
    if pinned:
        state.role = pinned
    elif not str(state.category or "").strip():
        state.category = infer_delegate_category(state.task)
    if not pinned:
        apply_category_resolver(state)
    apply_user_role_override(state)
    inject_handoff_block(state)
    inject_verify_checklist(state)
    inject_production_playbook_bridge(state)
    if state.bridge is not None:
        state.bridge.notify_delegate_start(state.role, preview=state.task[:80])
    check_delegate_depth(state)


__all__ = [
    "apply_category_resolver",
    "build_handoff_block_text",
    "check_delegate_depth",
    "infer_delegate_category",
    "inject_handoff_block",
    "inject_production_playbook_bridge",
    "inject_verify_checklist",
    "prepare_delegate_task",
]

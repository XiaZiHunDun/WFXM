from __future__ import annotations

from typing import TYPE_CHECKING

from butler.core.best_effort import safe_best_effort
from butler.core.hook_context_adapter import adapt_hook_context_lines
from butler.core.intent_keywords import detect_intent_banner
from butler.core.mode_classifier import detect_mode_suggestion_banner
from butler.core.session_recall_intent import (
    detect_local_project_inventory_banner,
    detect_session_read_recall_banner,
    is_local_project_inventory_intent,
    is_session_read_recall_intent,
)
from butler.core.task_route_hints import detect_cc_route_banner
from butler.gateway.hooks import apply_pre_llm_context

from .state import LockedTurnState

if TYPE_CHECKING:
    from butler.gateway.message_handler import ButlerMessageHandler


def _collect_ephemeral_gateway_banners(
    handler: "ButlerMessageHandler",
    state: LockedTurnState,
) -> list[str]:
    ephemeral_parts: list[str] = []

    def _intent_banner() -> None:
        banner = detect_intent_banner(state.text)
        if banner:
            ephemeral_parts.append(banner)
            state.health["intent_keyword_banner"] = True

    safe_best_effort(_intent_banner, label="locked_phases.intent_banner")

    def _recall_banner() -> None:
        state.session_read_recall_gate = is_session_read_recall_intent(state.text)
        pm = handler._orchestrator.project_manager
        proj = pm.get_current(session_key=state.session_key)
        ws = getattr(proj, "workspace", None) if proj else None
        banner = detect_session_read_recall_banner(
            state.text,
            state.session_key,
            workspace=ws,
        )
        if banner:
            ephemeral_parts.append(banner)
            state.health["session_read_recall_banner"] = True

    safe_best_effort(_recall_banner, label="locked_phases.recall_banner")

    def _inventory_banner() -> None:
        state.local_project_inventory_gate = is_local_project_inventory_intent(state.text)
        pm = handler._orchestrator.project_manager
        proj = pm.get_current(session_key=state.session_key)
        ws = getattr(proj, "workspace", None) if proj else None
        banner = detect_local_project_inventory_banner(state.text, workspace=ws)
        if banner:
            ephemeral_parts.append(banner)
            state.health["local_project_inventory_banner"] = True

    safe_best_effort(_inventory_banner, label="locked_phases.inventory_banner")

    def _mode_banner() -> None:
        banner = detect_mode_suggestion_banner(state.text, session_key=state.session_key)
        if banner:
            ephemeral_parts.append(banner)
            state.health["mode_classifier_banner"] = True

    safe_best_effort(_mode_banner, label="locked_phases.mode_banner")

    def _cc_banner() -> None:
        banner = detect_cc_route_banner(state.text)
        if banner:
            ephemeral_parts.append(banner)
            state.health["cc_route_banner"] = True

    safe_best_effort(_cc_banner, label="locked_phases.cc_route_banner")
    return ephemeral_parts


def _phase_augment_prompt(
    handler: "ButlerMessageHandler",
    state: LockedTurnState,
) -> None:
    state.augmented = apply_pre_llm_context(
        handler._orchestrator.inject_skill_context(state.text, diagnostics=state.health),
        session_key=state.session_key,
        orchestrator=handler._orchestrator,
    )
    ephemeral_parts = _collect_ephemeral_gateway_banners(handler, state)
    if ephemeral_parts:
        state.ephemeral_system = "\n\n".join(ephemeral_parts)
    if state.prompt_hooks.additional_context:
        hook_ctx = adapt_hook_context_lines(
            state.prompt_hooks.additional_context,
            source="user_prompt_submit_hook",
        )
        if hook_ctx:
            state.augmented = f"{hook_ctx}\n\n{state.augmented}"

"""R1-6 in-session pipeline phases for ``ButlerMessageHandler._handle_message_locked``.

Audit source: ``docs/reviews/project-deep-audit-2026-06-r1to8.md`` §R1-6

The original ``_handle_message_locked`` (lines 619-916, ~272 non-blank
lines) was a god method that mixed the natural-language normalizer
fan-out, slash command dispatch, UserPromptSubmit hooks, skill
context injection, ephemeral banners, loop budget resolution, hygiene
compression, memory prefetch, turn execution, post-turn memory sync,
outbound telemetry, and error-card rendering — all in one big
``with use_execution_context()`` block with a deeply nested try/except.

This module exposes the **in-session** pipeline as composable phase
functions operating on a mutable :class:`LockedTurnState` carrier.
The handler is reduced to a thin orchestrator that runs the phases
in order, with one try/except wrapping the whole turn for telemetry.

Post-condition: every phase helper is a thin orchestrator under 50
source lines (R1-5.2 size contract — see
``tests/test_message_handler_split.py``).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Optional

if TYPE_CHECKING:
    from butler.core.agent_loop import AgentLoop, LoopResult
    from butler.gateway.message_handler import ButlerMessageHandler

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Carrier — mutable per-turn state shared between phases.
# ---------------------------------------------------------------------------

@dataclass
class LockedTurnState:
    """Mutable carrier for one in-session turn.

    Phases mutate fields on this object. The orchestrator is
    responsible for initializing inputs and reading the final
    ``out`` after the run.
    """

    # Inputs (set by the orchestrator)
    text: str
    session_key: str
    platform: str
    external_id: str | None
    # Derived during the run
    loop_role: str = ""
    health: dict[str, Any] = field(default_factory=dict)
    augmented: str = ""
    ephemeral_system: Optional[str] = None
    prompt_hooks: Any = None
    loop: Any = None  # AgentLoop
    original_loop_config: Any = None
    max_out: Optional[int] = None
    run_callbacks: Any = None
    result: Any = None  # LoopResult
    out: str = ""
    turn_started: float = 0.0
    turn_elapsed: float = 0.0


# ---------------------------------------------------------------------------
# Phase 1 — natural-language normalizers + slash command dispatch.
# ---------------------------------------------------------------------------

# The list mirrors the 8 normalizers originally iterated inline at
# ``_handle_message_locked:632-651``. Extracting it to a module-level
# constant makes the order explicit and testable.
NORMALIZERS: tuple[Callable[[str], Optional[str]], ...] = (
    # imported lazily to avoid forcing handler_helpers on every import
    lambda: None,  # placeholder, populated in _load_normalizers()
)


def _load_normalizers() -> tuple[Callable[[str], Optional[str]], ...]:
    from butler.gateway.handler_helpers import (
        _normalize_contacts_request,
        _normalize_detail_request,
        _normalize_expense_request,
        _normalize_habits_request,
        _normalize_memo_request,
        _normalize_new_session_request,
        _normalize_status_request,
        _normalize_switch_request,
    )

    return (
        _normalize_detail_request,
        _normalize_switch_request,
        _normalize_status_request,
        _normalize_new_session_request,
        _normalize_memo_request,
        _normalize_contacts_request,
        _normalize_expense_request,
        _normalize_habits_request,
    )


def _phase_apply_normalizers_and_slash(
    handler: "ButlerMessageHandler",
    state: LockedTurnState,
) -> Optional[str]:
    """Phase: run the 8 NL normalizers + slash command dispatcher.

    Returns the first non-None response (early return).
    """
    for normalizer in _load_normalizers():
        cmd = normalizer(state.text)
        if cmd is not None:
            response = handler._handle_command(
                cmd,
                session_key=state.session_key,
                platform=state.platform,
                external_id=state.external_id,
            )
            if response is not None:
                return response
    if state.text.startswith("/"):
        response = handler._handle_command(
            state.text,
            session_key=state.session_key,
            platform=state.platform,
            external_id=state.external_id,
        )
        if response is not None:
            return response
    return None


# ---------------------------------------------------------------------------
# Phase 2 — UserPromptSubmit hooks (early return on blocked).
# ---------------------------------------------------------------------------

def _phase_apply_prompt_hooks(state: LockedTurnState) -> Optional[str]:
    """Phase: UserPromptSubmit hook runner. Returns a block message or None."""
    from butler.hooks.runner import run_user_prompt_submit_hooks

    state.prompt_hooks = run_user_prompt_submit_hooks(
        state.text.strip(),
        session_key=state.session_key,
        platform=state.platform,
    )
    if state.prompt_hooks.blocked:
        return state.prompt_hooks.block_message
    if state.prompt_hooks.prevent_continuation:
        return state.prompt_hooks.stop_message or "已停止（UserPromptSubmit hook）"
    return None


# ---------------------------------------------------------------------------
# Phase 3 — inject skill context + ephemeral system banners.
# ---------------------------------------------------------------------------

def _phase_augment_prompt(
    handler: "ButlerMessageHandler",
    state: LockedTurnState,
) -> None:
    """Phase: skill-context + pre-LLM hook + ephemeral banners."""
    from butler.gateway.hooks import apply_pre_llm_context

    state.augmented = apply_pre_llm_context(
        handler._orchestrator.inject_skill_context(state.text, diagnostics=state.health),
        session_key=state.session_key,
        orchestrator=handler._orchestrator,
    )
    ephemeral_parts: list[str] = []
    try:
        from butler.core.intent_keywords import detect_intent_banner

        intent_banner = detect_intent_banner(state.text)
        if intent_banner:
            ephemeral_parts.append(intent_banner)
            state.health["intent_keyword_banner"] = True
    except Exception as exc:
        logger.debug("Intent keyword detection skipped: %s", exc)
    try:
        from butler.core.mode_classifier import detect_mode_suggestion_banner

        mode_banner = detect_mode_suggestion_banner(state.text, session_key=state.session_key)
        if mode_banner:
            ephemeral_parts.append(mode_banner)
            state.health["mode_classifier_banner"] = True
    except Exception as exc:
        logger.debug("Mode classifier detection skipped: %s", exc)
    if ephemeral_parts:
        state.ephemeral_system = "\n\n".join(ephemeral_parts)
    if state.prompt_hooks.additional_context:
        hook_ctx = "\n\n".join(state.prompt_hooks.additional_context)
        state.augmented = f"{hook_ctx}\n\n{state.augmented}"


# ---------------------------------------------------------------------------
# Phase 4 — initialize loop_role and health dict for the turn.
# ---------------------------------------------------------------------------

def _phase_init_loop_role(
    handler: "ButlerMessageHandler",
    state: LockedTurnState,
) -> None:
    """Phase: resolve ``loop_role`` and seed the per-turn health dict."""
    from butler.plan.mode import is_plan_mode
    from butler.project.lead import gateway_loop_role

    pm = handler._orchestrator.project_manager
    proj_name = pm.resolve_active_project_name(session_key=state.session_key)
    proj = pm.get_current(session_key=state.session_key)
    state.loop_role = gateway_loop_role(proj_name, project=proj)
    if is_plan_mode(state.session_key):
        state.loop_role = "plan"
    state.health.update(
        {
            "session_key": state.session_key,
            "platform": state.platform,
            "platform_chat_id": state.external_id or "",
            "last_user_query": state.text.strip()[:500],
            "gateway_agent_role": state.loop_role,
        }
    )


# ---------------------------------------------------------------------------
# Phase 5a — loop-message sequence validation.
# ---------------------------------------------------------------------------

def _phase_validate_loop_messages(state: LockedTurnState) -> Optional[str]:
    """Phase: validate the loop's message sequence before this turn.

    Returns a blocking reply on validation failure (rare; usually the
    loop is reset by the validator itself).
    """
    try:
        from butler.gateway.inbound_validate import validate_loop_messages_before_turn

        seq_err = validate_loop_messages_before_turn(state.loop.messages)
        if seq_err:
            return seq_err
    except Exception as exc:
        logger.debug("Loop message validation skipped: %s", exc)
    return None


# ---------------------------------------------------------------------------
# Phase 5b — turn budget resolution.
# ---------------------------------------------------------------------------

def _phase_resolve_turn_budget(state: LockedTurnState) -> None:
    """Phase: resolve the per-turn token budget and update loop.config."""
    from butler.core.turn_token_budget import resolve_turn_budget

    state.loop.config, turn_budget, state.augmented = resolve_turn_budget(
        state.augmented, state.loop.config,
    )
    if turn_budget:
        state.health["turn_token_budget"] = turn_budget
        state.health["turn_max_iterations"] = state.loop.config.max_iterations


# ---------------------------------------------------------------------------
# Phase 5c — hygiene compression of the loop's context.
# ---------------------------------------------------------------------------

def _phase_hygiene_compress(
    handler: "ButlerMessageHandler",
    state: LockedTurnState,
) -> None:
    """Phase: hygiene compression + diagnostics capture for the loop."""
    try:
        from butler.core.model_context import resolve_max_output_tokens

        state.max_out = resolve_max_output_tokens(
            handler._orchestrator,
            session_key=state.session_key,
            role=state.loop_role,
        )
        hygiene_compressed = state.loop.hygiene_compress_if_needed(
            max_output_tokens=state.max_out,
        )
        state.health["hygiene_compressed"] = hygiene_compressed
        state.health.update({
            k: v for k, v in getattr(state.loop, "diagnostics", {}).items()
            if str(k).startswith(("hygiene_", "context_"))
        })
    except Exception as exc:
        state.health["hygiene_error"] = str(exc)
        logger.warning("Gateway hygiene compression skipped: %s", exc)


# ---------------------------------------------------------------------------
# Phase 5d — memory prefetch + run-callback wiring.
# ---------------------------------------------------------------------------

def _phase_prefetch_and_callbacks(
    handler: "ButlerMessageHandler",
    state: LockedTurnState,
) -> None:
    """Phase: attach memory prefetch + wire up bridge run callbacks."""
    from butler.gateway.handler_helpers import _gateway_run_callbacks
    from butler.session.lifecycle import attach_turn_memory_prefetch

    attach_turn_memory_prefetch(
        state.loop,
        handler._orchestrator,
        state.text,
        role=state.loop_role,
        diagnostics=state.health,
    )
    state.run_callbacks = _gateway_run_callbacks()


# ---------------------------------------------------------------------------
# Phase 6 — execute the loop (with todo/goal continuation).
# ---------------------------------------------------------------------------

def _phase_execute_turn(state: LockedTurnState) -> None:
    """Phase: run the AgentLoop with todo/goal continuation fallback."""
    ephemeral_system = state.ephemeral_system

    def _run_turn(msg: str) -> "LoopResult":
        run_kwargs: dict[str, Any] = {}
        if ephemeral_system:
            run_kwargs["ephemeral_system"] = ephemeral_system
        try:
            if state.run_callbacks is not None:
                return state.loop.run(
                    msg, run_callbacks=state.run_callbacks, **run_kwargs,
                )
            return state.loop.run(msg, **run_kwargs)
        except TypeError:
            if state.run_callbacks is not None:
                return state.loop.run(msg, run_callbacks=state.run_callbacks)
            return state.loop.run(msg)

    try:
        from butler.core.goal_loop import maybe_run_goal_continuation
        from butler.core.todo_continuation import run_with_todo_continuation

        result = run_with_todo_continuation(
            state.loop,
            state.augmented,
            state.session_key,
            run_fn=_run_turn,
            run_callbacks=state.run_callbacks,
        )
        result = maybe_run_goal_continuation(
            state.loop,
            result,
            state.session_key,
            run_fn=_run_turn,
        )
    except Exception as exc:
        logger.debug("Todo/goal continuation fallback: %s", exc)
        result = _run_turn(state.augmented)
    state.result = result


# ---------------------------------------------------------------------------
# Phase 7 — finalize turn: diagnostics, memory sync, queue, health.
# ---------------------------------------------------------------------------

def _phase_finalize_turn(
    handler: "ButlerMessageHandler",
    state: LockedTurnState,
) -> None:
    """Phase: capture diagnostics + memory sync + queue + set health."""
    from butler.core.agent_loop import LoopStatus

    state.health["loop"] = dict(getattr(state.result, "diagnostics", {}) or {})
    if getattr(state.result, "transition_reason", ""):
        state.health["loop_transition_reason"] = state.result.transition_reason
    if state.result.status == LoopStatus.INTERRUPTED:
        try:
            from butler.core.auto_continue import capture_auto_continue_pending

            capture_auto_continue_pending(
                state.session_key,
                user_preview=state.augmented,
                reason="interrupt",
                diagnostics=state.health.get("loop")
                if isinstance(state.health.get("loop"), dict)
                else None,
            )
        except Exception as exc:
            logger.debug("Auto continue capture skipped: %s", exc)
    from butler.session.lifecycle import sync_turn_memory

    sync_result = sync_turn_memory(
        handler._orchestrator,
        state.text,
        state.result.final_response or "",
        interrupted=state.result.status == LoopStatus.INTERRUPTED,
        status=state.result.status,
        session_id=state.session_key,
    )
    state.health["memory_sync"] = sync_result
    from butler.session.lifecycle import queue_prefetch_after_turn

    queue_prefetch_after_turn(
        handler._orchestrator,
        state.text,
        role=state.loop_role,
        session_id=state.session_key,
    )
    handler._session_registry.set_health(state.session_key, state.health)


# ---------------------------------------------------------------------------
# Phase 8 — format the final response + record outbound telemetry.
# ---------------------------------------------------------------------------

def _phase_format_turn_response(
    handler: "ButlerMessageHandler",
    state: LockedTurnState,
    welcome_prefix: str = "",
) -> None:
    """Phase: format response + record outbound telemetry + welcome prefix."""
    import time as _time

    state.out = handler._format_response(state.result, state.platform)
    state.turn_elapsed = _time.monotonic() - state.turn_started
    from butler.gateway.outbound_bridge import get_current_bridge

    br = get_current_bridge()
    if br is not None:
        br.record_turn_elapsed(state.turn_elapsed)
        state.health["outbound_events"] = br.recent_outbound_events()[-8:]
    try:
        from butler.gateway.item_event_sink import recent_thread_items

        items = recent_thread_items(8)
        if items:
            state.health["thread_items"] = items
    except Exception as exc:
        logger.debug("Thread items collection skipped: %s", exc)
    logger.info(
        "Gateway turn done session=%s elapsed=%.1fs out_len=%d",
        state.session_key,
        state.turn_elapsed,
        len(state.out or ""),
    )
    if welcome_prefix:
        state.out = f"{welcome_prefix}\n\n---\n\n{state.out}" if state.out else welcome_prefix


# ---------------------------------------------------------------------------
# Phase 9 — render an error card from an exception.
# ---------------------------------------------------------------------------

def _phase_format_error_card(exc: BaseException, turn_elapsed: float) -> Optional[str]:
    """Phase: build a structured error card for the failure reply.

    Returns ``None`` when the renderer itself fails (caller falls back
    to ``format_gateway_user_error``).
    """
    try:
        from butler.gateway.error_cards import format_error_card

        exc_type = type(exc).__name__
        if "timeout" in exc_type.lower() or "Timeout" in exc_type:
            return format_error_card(
                "delegate_timeout",
                role="agent",
                elapsed=round(turn_elapsed),
            )
        if "Permission" in exc_type:
            return format_error_card(
                "permission_deny",
                tool="message_handler",
                reason=str(exc)[:200],
            )
        return format_error_card(
            "tool_error",
            tool="message_handler",
            error=str(exc),
        )
    except Exception:
        return None

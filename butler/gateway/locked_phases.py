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
    session_read_recall_gate: bool = False


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


def _phase_apply_correction_intent(
    handler: "ButlerMessageHandler",
    state: LockedTurnState,
) -> Optional[str]:
    """Phase: H4 owner correction intent — persist without LLM."""
    try:
        from butler.core.correction_intent import try_handle_correction_intent

        return try_handle_correction_intent(
            handler._orchestrator,
            state.text,
            session_key=state.session_key,
        )
    except Exception as exc:
        logger.debug("Correction intent skipped: %s", exc)
        return None


def _phase_apply_github_issues_intent(
    handler: "ButlerMessageHandler",
    state: LockedTurnState,
) -> Optional[str]:
    """Phase: EXT-4 GitHub issues list — MCP direct reply without LLM."""
    del handler
    try:
        from butler.mcp.github_grounding import try_handle_github_issues_intent

        return try_handle_github_issues_intent(state.text)
    except Exception as exc:
        logger.debug("GitHub issues intent skipped: %s", exc)
        return None


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

def _collect_ephemeral_gateway_banners(
    handler: "ButlerMessageHandler",
    state: LockedTurnState,
) -> list[str]:
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
        from butler.core.session_recall_intent import (
            detect_session_read_recall_banner,
            is_session_read_recall_intent,
        )

        state.session_read_recall_gate = is_session_read_recall_intent(state.text)
        pm = handler._orchestrator.project_manager
        proj = pm.get_current(session_key=state.session_key)
        ws = getattr(proj, "workspace", None) if proj else None
        recall_banner = detect_session_read_recall_banner(
            state.text,
            state.session_key,
            workspace=ws,
        )
        if recall_banner:
            ephemeral_parts.append(recall_banner)
            state.health["session_read_recall_banner"] = True
    except Exception as exc:
        logger.debug("Session read recall banner skipped: %s", exc)
    try:
        from butler.core.mode_classifier import detect_mode_suggestion_banner

        mode_banner = detect_mode_suggestion_banner(state.text, session_key=state.session_key)
        if mode_banner:
            ephemeral_parts.append(mode_banner)
            state.health["mode_classifier_banner"] = True
    except Exception as exc:
        logger.debug("Mode classifier detection skipped: %s", exc)
    return ephemeral_parts


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
    ephemeral_parts = _collect_ephemeral_gateway_banners(handler, state)
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
    try:
        from butler.memory.memory_metrics import get_collector
        from butler.memory.metrics_persist import load_persisted_metrics

        load_persisted_metrics()
        get_collector().start_session(state.session_key)
    except Exception:
        pass


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
            from butler.core.tool_pair_repair import repair_tool_pairs_json_safe

            repaired, count = repair_tool_pairs_json_safe(list(state.loop.messages))
            if count > 0:
                state.loop.messages = repaired
                seq_err = validate_loop_messages_before_turn(state.loop.messages)
                if not seq_err:
                    state.health["tool_pair_repair_pre_turn"] = count
                    return None
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


def _chain_callbacks(base: Any, extra: Any) -> Any:
    """Chain two LoopCallbacks so both get called for each event."""
    from butler.core.loop_types import LoopCallbacks

    if base is None:
        return extra
    if extra is None:
        return base

    def _chain(name: str) -> Any:
        fn_a = getattr(base, name, None)
        fn_b = getattr(extra, name, None)
        if fn_a is None:
            return fn_b
        if fn_b is None:
            return fn_a

        def chained(*args: Any, **kwargs: Any) -> Any:
            try:
                fn_a(*args, **kwargs)
            except Exception:
                pass
            try:
                return fn_b(*args, **kwargs)
            except Exception:
                pass
            return None

        return chained

    return LoopCallbacks(**{
        f.name: _chain(f.name) for f in LoopCallbacks.__dataclass_fields__.values()
    })


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

    try:
        from butler.ops.langfuse_tracer import langfuse_enabled
        if langfuse_enabled():
            from butler.ops.langfuse_tracer import get_current_trace, langfuse_callbacks
            from butler.core.loop_types import LoopCallbacks

            lf_cbs = langfuse_callbacks(session_key=state.session_key)
            if lf_cbs:
                lf_loop_cbs = LoopCallbacks(**lf_cbs)
                state.run_callbacks = _chain_callbacks(state.run_callbacks, lf_loop_cbs)
            ctx = get_current_trace(session_key=state.session_key)
            if ctx is not None:
                ctx.on_gateway_inbound(state.session_key, state.platform, len(state.text))
    except Exception as exc:
        logger.debug("LangFuse callback wiring skipped: %s", exc)


# ---------------------------------------------------------------------------
# Phase 6 — execute the loop (with todo/goal continuation).
# ---------------------------------------------------------------------------

def _phase_execute_turn(state: LockedTurnState) -> None:
    """Phase: run the AgentLoop with todo/goal continuation fallback."""
    from butler.execution_context import use_session_read_recall_gate

    with use_session_read_recall_gate(state.session_read_recall_gate):
        _phase_execute_turn_inner(state)


def _phase_execute_turn_inner(state: LockedTurnState) -> None:
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

def _phase_finalize_loop_diagnostics(state: LockedTurnState) -> None:
    loop_diag = dict(getattr(state.result, "diagnostics", {}) or {})
    state.health["loop"] = loop_diag
    if getattr(state.result, "transition_reason", ""):
        state.health["loop_transition_reason"] = state.result.transition_reason
    try:
        from butler.core.compaction_status import promote_compaction_diagnostics_to_health
        from butler.memory.memory_metrics import get_collector

        promote_compaction_diagnostics_to_health(state.health, loop_diag)
        mm = get_collector().get_session_metrics(state.session_key)
        if "error" not in mm:
            state.health["memory_metrics"] = mm.get("computed") or {}
            for key in (
                "facts_pre_compact",
                "facts_post_compact",
                "anchor_facts_pre",
                "anchor_facts_post",
                "prefetch_turns",
                "prefetch_hits",
            ):
                if key in mm:
                    state.health[key] = mm[key]
    except Exception as exc:
        logger.debug("Compaction/memory diagnostics promote skipped: %s", exc)


def _phase_finalize_interrupt_capture(state: LockedTurnState) -> None:
    from butler.core.agent_loop import LoopStatus

    if state.result.status != LoopStatus.INTERRUPTED:
        return
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


def _phase_finalize_memory_sync(
    handler: "ButlerMessageHandler",
    state: LockedTurnState,
) -> None:
    from butler.core.agent_loop import LoopStatus
    from butler.session.lifecycle import queue_prefetch_after_turn, sync_turn_memory

    sync_result = sync_turn_memory(
        handler._orchestrator,
        state.text,
        state.result.final_response or "",
        interrupted=state.result.status == LoopStatus.INTERRUPTED,
        status=state.result.status,
        session_id=state.session_key,
    )
    state.health["memory_sync"] = sync_result
    queue_prefetch_after_turn(
        handler._orchestrator,
        state.text,
        role=state.loop_role,
        session_id=state.session_key,
    )


def _phase_finalize_eval_observability(state: LockedTurnState) -> None:
    try:
        from butler.ops.langfuse_tracer import (
            end_trace,
            flush_langfuse,
            get_current_trace,
            langfuse_enabled,
        )

        if langfuse_enabled():
            trace_id = ""
            ctx = get_current_trace(session_key=state.session_key)
            if ctx is not None:
                trace_id = ctx.trace_id
            from butler.ops.eval_turn import extract_tools_used, push_turn_scores

            multi, eval_report = push_turn_scores(
                user_text=state.text,
                response_text=state.result.final_response or "",
                tools_used=extract_tools_used(getattr(state.result, "diagnostics", None)),
                session_id=state.session_key,
                trace_id=trace_id,
            )
            state.health["eval_turn"] = {
                "overall": round(multi.overall, 3),
                "dims": multi.by_dimension(),
                "scores_pushed": eval_report.scores_pushed,
            }
            end_trace(session_key=state.session_key, result=state.result)
            flush_langfuse()
    except Exception as exc:
        logger.debug("LangFuse turn-end flush skipped: %s", exc)
    try:
        from butler.memory.metrics_persist import flush_memory_metrics

        flush_memory_metrics(force=True)
    except Exception as exc:
        logger.debug("memory metrics flush skipped: %s", exc)


def _phase_finalize_prefetch_pr(state: LockedTurnState) -> None:
    try:
        from butler.memory.prefetch_retrieval_metrics import finalize_prefetch_retrieval_metrics

        finalize_prefetch_retrieval_metrics(
            state.session_key,
            state.result.final_response or "",
            state.health,
        )
    except Exception as exc:
        logger.debug("Prefetch P_r finalize skipped: %s", exc)


def _phase_finalize_turn(
    handler: "ButlerMessageHandler",
    state: LockedTurnState,
) -> None:
    """Phase: capture diagnostics + memory sync + queue + set health."""
    _phase_finalize_loop_diagnostics(state)
    _phase_finalize_interrupt_capture(state)
    _phase_finalize_memory_sync(handler, state)
    _phase_finalize_prefetch_pr(state)
    try:
        from butler.core.memory_source_surface import snapshot_last_turn_memory_sources

        snapshot_last_turn_memory_sources(state.health)
    except Exception as exc:
        logger.debug("Memory sources snapshot skipped: %s", exc)
    handler._session_registry.set_health(state.session_key, state.health)
    _phase_finalize_eval_observability(state)


# ---------------------------------------------------------------------------
# Phase 8 — format the final response + record outbound telemetry.
# ---------------------------------------------------------------------------

def _record_format_turn_langfuse(state: LockedTurnState) -> None:
    try:
        from butler.ops.langfuse_tracer import get_current_trace, langfuse_enabled

        if langfuse_enabled():
            ctx = get_current_trace(session_key=state.session_key)
            if ctx is not None:
                ctx.on_gateway_outbound(state.session_key, len(state.out or ""), state.turn_elapsed)
    except Exception:
        pass


def _append_format_turn_extras(state: LockedTurnState, welcome_prefix: str = "") -> None:
    if welcome_prefix:
        state.out = f"{welcome_prefix}\n\n---\n\n{state.out}" if state.out else welcome_prefix
    try:
        if getattr(state.loop, "_session_recovery_pending", None) is True:
            from butler.core.session_hydration import recovery_notice_text

            note = recovery_notice_text()
            state.out = f"{note}\n\n{state.out}" if state.out else note
            setattr(state.loop, "_session_recovery_pending", False)
            state.health["session_recovery_notice"] = True
    except Exception as exc:
        logger.debug("Session recovery notice skipped: %s", exc)
    try:
        from butler.core.turn_summary_line import maybe_prepend_turn_summary

        state.out = maybe_prepend_turn_summary(state.session_key, state.out or "")
    except Exception as exc:
        logger.debug("Turn summary line skipped: %s", exc)
    try:
        from butler.core.memory_recap_line import maybe_prepend_memory_recap

        state.out = maybe_prepend_memory_recap(
            state.session_key,
            state.out or "",
            health=state.health,
        )
    except Exception as exc:
        logger.debug("Memory recap line skipped: %s", exc)


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
    _record_format_turn_langfuse(state)
    _append_format_turn_extras(state, welcome_prefix)


# ---------------------------------------------------------------------------
# Phase 9 — render an error card from an exception.
# ---------------------------------------------------------------------------

def _phase_format_error_card(exc: BaseException, turn_elapsed: float) -> Optional[str]:
    """Phase: build a structured error card for the failure reply.

    Returns ``None`` when the renderer itself fails (caller falls back
    to ``format_gateway_user_error``). Audit R2-16: the previous
    ``except Exception: return None`` was completely silent — if the
    error-card renderer itself broke, operators had no signal. We now
    log at ERROR with full traceback so the failure is visible while
    preserving the caller's fallback contract.
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
        logger.error("error card formatting failed", exc_info=True)
        return None

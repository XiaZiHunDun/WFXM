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
from typing import TYPE_CHECKING, Any, Callable, Optional, cast

if TYPE_CHECKING:
    from butler.core.agent_loop import AgentLoop, LoopResult
    from butler.gateway.message_handler import ButlerMessageHandler

from butler.core.auto_continue import capture_auto_continue_pending
from butler.core.compaction_status import promote_compaction_diagnostics_to_health
from butler.core.correction_intent import try_handle_correction_intent
from butler.core.goal_loop import maybe_run_goal_continuation
from butler.core.hook_context_adapter import adapt_hook_context_lines
from butler.core.intent_keywords import detect_intent_banner
from butler.core.loop_types import LoopCallbacks, LoopStatus
from butler.core.memory_recap_line import maybe_prepend_memory_recap
from butler.core.memory_source_surface import snapshot_last_turn_memory_sources
from butler.core.mode_classifier import detect_mode_suggestion_banner
from butler.core.model_context import resolve_max_output_tokens
from butler.core.session_hydration import recovery_notice_text
from butler.core.session_recall_intent import (
    detect_session_read_recall_banner,
    is_session_read_recall_intent,
)
from butler.core.task_route_hints import detect_cc_route_banner
from butler.core.todo_continuation import run_with_todo_continuation
from butler.core.tool_pair_repair import repair_tool_pairs_json_safe
from butler.core.transform_feedback import maybe_apply_turn_feedback
from butler.core.turn_summary_line import maybe_prepend_turn_summary
from butler.core.turn_token_budget import resolve_turn_budget
from butler.execution_context import use_session_read_recall_gate
from butler.gateway.hooks import apply_pre_llm_context
from butler.gateway.inbound_validate import validate_loop_messages_before_turn
from butler.gateway.locked_phases_ops import format_gateway_error_card, run_hygiene_compress
from butler.gateway.outbound_bridge import get_current_bridge
from butler.gateway.item_event_sink import recent_thread_items
from butler.hooks.runner import run_user_prompt_submit_hooks
from butler.mcp.github_grounding import try_handle_github_issues_intent
from butler.memory.prefetch_retrieval_metrics import finalize_prefetch_retrieval_metrics
from butler.ops import langfuse_tracer
from butler.ops.eval_turn import extract_tools_used, push_turn_scores
from butler.plan.mode import is_plan_mode
from butler.project.lead import gateway_loop_role
from butler.session.lifecycle import (
    attach_turn_memory_prefetch,
    queue_prefetch_after_turn,
    sync_turn_memory,
)
from butler.core.best_effort import safe_best_effort
from butler.gateway.handler_helpers import (
    _gateway_run_callbacks,
    _normalize_contacts_request,
    _normalize_detail_request,
    _normalize_expense_request,
    _normalize_habits_request,
    _normalize_memo_request,
    _normalize_new_session_request,
    _normalize_status_request,
    _normalize_switch_request,
)
from butler.memory.memory_metrics import get_collector as _memory_metrics_collector
from butler.memory.metrics_persist import flush_memory_metrics, load_persisted_metrics

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
# ``_handle_message_locked:632-651``. Order lives in ``_load_normalizers()``.


def _load_normalizers() -> tuple[Callable[[str], Optional[str]], ...]:
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

    def _run() -> Optional[str]:
        return cast(
            Optional[str],
            try_handle_correction_intent(
                handler._orchestrator,
                state.text,
                session_key=state.session_key,
            ),
        )

    return cast(
        Optional[str],
        safe_best_effort(_run, label="locked_phases.correction_intent"),
    )


def _phase_apply_github_issues_intent(
    handler: "ButlerMessageHandler",
    state: LockedTurnState,
) -> Optional[str]:
    """Phase: EXT-4 GitHub issues list — MCP direct reply without LLM."""
    del handler

    def _run() -> Optional[str]:
        return cast(Optional[str], try_handle_github_issues_intent(state.text))

    return cast(
        Optional[str],
        safe_best_effort(_run, label="locked_phases.github_issues_intent"),
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
                return cast(str, response)
    if state.text.startswith("/"):
        response = handler._handle_command(
            state.text,
            session_key=state.session_key,
            platform=state.platform,
            external_id=state.external_id,
        )
        if response is not None:
            return cast(str, response)
    return None


# ---------------------------------------------------------------------------
# Phase 2 — UserPromptSubmit hooks (early return on blocked).
# ---------------------------------------------------------------------------

def _phase_apply_prompt_hooks(state: LockedTurnState) -> Optional[str]:
    """Phase: UserPromptSubmit hook runner. Returns a block message or None."""
    state.prompt_hooks = run_user_prompt_submit_hooks(
        state.text.strip(),
        session_key=state.session_key,
        platform=state.platform,
    )
    if state.prompt_hooks.blocked:
        return cast(str, state.prompt_hooks.block_message)
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
    """Phase: skill-context + pre-LLM hook + ephemeral banners."""
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


# ---------------------------------------------------------------------------
# Phase 4 — initialize loop_role and health dict for the turn.
# ---------------------------------------------------------------------------

def _phase_init_loop_role(
    handler: "ButlerMessageHandler",
    state: LockedTurnState,
) -> None:
    """Phase: resolve ``loop_role`` and seed the per-turn health dict."""
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
    def _start_metrics_session() -> None:
        load_persisted_metrics()
        _memory_metrics_collector().start_session(state.session_key)

    safe_best_effort(_start_metrics_session, label="locked_phases.memory_metrics")


# ---------------------------------------------------------------------------
# Phase 5a — loop-message sequence validation.
# ---------------------------------------------------------------------------

def _phase_validate_loop_messages(state: LockedTurnState) -> Optional[str]:
    """Phase: validate the loop's message sequence before this turn.

    Returns a blocking reply on validation failure (rare; usually the
    loop is reset by the validator itself).
    """

    def _validate() -> Optional[str]:
        seq_err = validate_loop_messages_before_turn(state.loop.messages)
        if seq_err:
            repaired, count = repair_tool_pairs_json_safe(list(state.loop.messages))
            if count > 0:
                state.loop.messages = repaired
                seq_err = validate_loop_messages_before_turn(state.loop.messages)
                if not seq_err:
                    state.health["tool_pair_repair_pre_turn"] = count
                    return None
            return cast(str, seq_err)
        return None

    return cast(
        Optional[str],
        safe_best_effort(
            _validate,
            label="locked_phases.validate_messages",
            default=None,
        ),
    )


# ---------------------------------------------------------------------------
# Phase 5b — turn budget resolution.
# ---------------------------------------------------------------------------

def _phase_resolve_turn_budget(state: LockedTurnState) -> None:
    """Phase: resolve the per-turn token budget and update loop.config."""
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

    def _compress() -> None:
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

    run_hygiene_compress(state, _compress)


def _chain_callbacks(base: Any, extra: Any) -> Any:
    """Chain two LoopCallbacks so both get called for each event."""
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
            safe_best_effort(
                lambda: fn_a(*args, **kwargs),
                label="locked_phases.callback_chain",
            )
            return safe_best_effort(
                lambda: fn_b(*args, **kwargs),
                label="locked_phases.callback_chain",
                default=None,
            )

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
    attach_turn_memory_prefetch(
        state.loop,
        handler._orchestrator,
        state.text,
        role=state.loop_role,
        diagnostics=state.health,
    )
    state.run_callbacks = _gateway_run_callbacks()

    def _wire_langfuse() -> None:
        if not langfuse_tracer.langfuse_enabled():
            return
        lf_cbs = langfuse_tracer.langfuse_callbacks(session_key=state.session_key)
        if lf_cbs:
            lf_loop_cbs = LoopCallbacks(**lf_cbs)
            state.run_callbacks = _chain_callbacks(state.run_callbacks, lf_loop_cbs)
        ctx = langfuse_tracer.get_current_trace(session_key=state.session_key)
        if ctx is not None:
            ctx.on_gateway_inbound(state.session_key, state.platform, len(state.text))

    safe_best_effort(_wire_langfuse, label="locked_phases.langfuse_callbacks")


# ---------------------------------------------------------------------------
# Phase 6 — execute the loop (with todo/goal continuation).
# ---------------------------------------------------------------------------

def _phase_execute_turn(state: LockedTurnState) -> None:
    """Phase: run the AgentLoop with todo/goal continuation fallback."""
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

    def _run_with_continuations() -> "LoopResult":
        result = run_with_todo_continuation(
            state.loop,
            state.augmented,
            state.session_key,
            run_fn=_run_turn,
            run_callbacks=state.run_callbacks,
        )
        return maybe_run_goal_continuation(
            state.loop,
            result,
            state.session_key,
            run_fn=_run_turn,
        )

    result = safe_best_effort(
        _run_with_continuations,
        label="locked_phases.todo_goal_continuation",
    )
    if result is None:
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
    def _promote_diag() -> None:
        promote_compaction_diagnostics_to_health(state.health, loop_diag)
        mm = _memory_metrics_collector().get_session_metrics(state.session_key)
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

    safe_best_effort(_promote_diag, label="locked_phases.compaction_diag")


def _phase_finalize_interrupt_capture(state: LockedTurnState) -> None:
    if state.result.status != LoopStatus.INTERRUPTED:
        return
    def _capture_interrupt() -> None:
        capture_auto_continue_pending(
            state.session_key,
            user_preview=state.augmented,
            reason="interrupt",
            diagnostics=state.health.get("loop")
            if isinstance(state.health.get("loop"), dict)
            else None,
        )

    safe_best_effort(_capture_interrupt, label="locked_phases.auto_continue_capture")


def _phase_finalize_memory_sync(
    handler: "ButlerMessageHandler",
    state: LockedTurnState,
) -> None:
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
    def _langfuse_turn_end() -> None:
        if not langfuse_tracer.langfuse_enabled():
            return
        trace_id = ""
        ctx = langfuse_tracer.get_current_trace(session_key=state.session_key)
        if ctx is not None:
            trace_id = ctx.trace_id
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

        def _transform_feedback() -> None:
            provider = ""
            loop = getattr(state.result, "loop", None)
            client = getattr(loop, "client", None) if loop else None
            if client is not None:
                provider = str(getattr(client, "provider_name", "") or "")
            actions = maybe_apply_turn_feedback(
                multi.by_dimension(),
                provider=provider,
            )
            if actions:
                state.health["transform_feedback"] = actions

        safe_best_effort(_transform_feedback, label="locked_phases.transform_feedback")
        langfuse_tracer.end_trace(session_key=state.session_key, result=state.result)
        langfuse_tracer.flush_langfuse()

    safe_best_effort(_langfuse_turn_end, label="locked_phases.langfuse_turn_end")

    safe_best_effort(
        lambda: flush_memory_metrics(force=True),
        label="locked_phases.memory_metrics_flush",
    )


def _phase_finalize_prefetch_pr(state: LockedTurnState) -> None:
    def _finalize() -> None:
        finalize_prefetch_retrieval_metrics(
            state.session_key,
            state.result.final_response or "",
            state.health,
        )

    safe_best_effort(_finalize, label="locked_phases.prefetch_pr_finalize")


def _phase_finalize_turn(
    handler: "ButlerMessageHandler",
    state: LockedTurnState,
) -> None:
    """Phase: capture diagnostics + memory sync + queue + set health."""
    _phase_finalize_loop_diagnostics(state)
    _phase_finalize_interrupt_capture(state)
    _phase_finalize_memory_sync(handler, state)
    _phase_finalize_prefetch_pr(state)

    def _snapshot_sources() -> None:
        snapshot_last_turn_memory_sources(state.health)

    safe_best_effort(_snapshot_sources, label="locked_phases.memory_sources_snapshot")
    handler._session_registry.set_health(state.session_key, state.health)
    _phase_finalize_eval_observability(state)


# ---------------------------------------------------------------------------
# Phase 8 — format the final response + record outbound telemetry.
# ---------------------------------------------------------------------------

def _record_format_turn_langfuse(state: LockedTurnState) -> None:
    def _record() -> None:
        if langfuse_tracer.langfuse_enabled():
            ctx = langfuse_tracer.get_current_trace(session_key=state.session_key)
            if ctx is not None:
                ctx.on_gateway_outbound(state.session_key, len(state.out or ""), state.turn_elapsed)

    safe_best_effort(_record, label="locked_phases.langfuse_outbound")


def _append_format_turn_extras(state: LockedTurnState, welcome_prefix: str = "") -> None:
    if welcome_prefix:
        state.out = f"{welcome_prefix}\n\n---\n\n{state.out}" if state.out else welcome_prefix

    def _recovery_notice() -> None:
        if getattr(state.loop, "_session_recovery_pending", None) is not True:
            return
        note = recovery_notice_text()
        state.out = f"{note}\n\n{state.out}" if state.out else note
        setattr(state.loop, "_session_recovery_pending", False)
        state.health["session_recovery_notice"] = True

    safe_best_effort(_recovery_notice, label="locked_phases.session_recovery_notice")

    def _turn_summary() -> None:
        state.out = maybe_prepend_turn_summary(state.session_key, state.out or "")

    safe_best_effort(_turn_summary, label="locked_phases.turn_summary_line")

    def _memory_recap() -> None:
        state.out = maybe_prepend_memory_recap(
            state.session_key,
            state.out or "",
            health=state.health,
        )

    safe_best_effort(_memory_recap, label="locked_phases.memory_recap_line")


def _phase_format_turn_response(
    handler: "ButlerMessageHandler",
    state: LockedTurnState,
    welcome_prefix: str = "",
) -> None:
    """Phase: format response + record outbound telemetry + welcome prefix."""
    import time as _time

    state.out = handler._format_response(state.result, state.platform)
    state.turn_elapsed = _time.monotonic() - state.turn_started
    br = get_current_bridge()
    if br is not None:
        br.record_turn_elapsed(state.turn_elapsed)
        state.health["outbound_events"] = br.recent_outbound_events()[-8:]

    def _thread_items() -> None:
        items = recent_thread_items(8)
        if items:
            state.health["thread_items"] = items

    safe_best_effort(_thread_items, label="locked_phases.thread_items")
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
    """Phase: build a structured error card for the failure reply."""
    return cast(
        Optional[str],
        format_gateway_error_card(exc, turn_elapsed),
    )

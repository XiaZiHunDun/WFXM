from __future__ import annotations

from typing import TYPE_CHECKING

from butler.core.auto_continue import capture_auto_continue_pending
from butler.core.best_effort import safe_best_effort
from butler.core.compaction_status import promote_compaction_diagnostics_to_health
from butler.core.loop_types import LoopStatus
from butler.core.memory_source_surface import snapshot_last_turn_memory_sources
from butler.core.transform_feedback import maybe_apply_turn_feedback
from butler.memory.memory_metrics import get_collector as _memory_metrics_collector
from butler.memory.metrics_persist import flush_memory_metrics
from butler.memory.prefetch_retrieval_metrics import finalize_prefetch_retrieval_metrics
from butler.ops import langfuse_tracer
from butler.ops.eval_turn import extract_tools_used, push_turn_scores
from butler.session.lifecycle import queue_prefetch_after_turn, sync_turn_memory

from .state import LockedTurnState

if TYPE_CHECKING:
    from butler.gateway.message_handler import ButlerMessageHandler


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
    _phase_finalize_loop_diagnostics(state)
    _phase_finalize_interrupt_capture(state)
    _phase_finalize_memory_sync(handler, state)
    _phase_finalize_prefetch_pr(state)

    def _snapshot_sources() -> None:
        snapshot_last_turn_memory_sources(state.health)

    safe_best_effort(_snapshot_sources, label="locked_phases.memory_sources_snapshot")
    handler._session_registry.set_health(state.session_key, state.health)
    _phase_finalize_eval_observability(state)

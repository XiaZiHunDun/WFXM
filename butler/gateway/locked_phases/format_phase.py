from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from butler.core.best_effort import safe_best_effort
from butler.core.memory_recap_line import maybe_prepend_memory_recap
from butler.core.session_hydration import recovery_notice_text
from butler.core.turn_summary_line import maybe_prepend_turn_summary
from butler.gateway.item_event_sink import recent_thread_items
from butler.gateway.outbound_bridge import get_current_bridge
from butler.ops import langfuse_tracer

from .state import LockedTurnState

if TYPE_CHECKING:
    from butler.gateway.message_handler import ButlerMessageHandler

logger = logging.getLogger(__name__)


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

from __future__ import annotations

from typing import TYPE_CHECKING, Optional, cast

from butler.core.best_effort import safe_best_effort
from butler.core.model_context import resolve_max_output_tokens
from butler.core.tool_pair_repair import repair_tool_pairs_json_safe
from butler.core.turn_token_budget import resolve_turn_budget
from butler.gateway.handler_helpers import _gateway_run_callbacks
from butler.gateway.inbound_validate import validate_loop_messages_before_turn
from butler.gateway.locked_phases_ops import run_hygiene_compress
from butler.ops import langfuse_tracer
from butler.session.lifecycle import attach_turn_memory_prefetch
from butler.core.loop_types import LoopCallbacks

from .state import LockedTurnState, _chain_callbacks

if TYPE_CHECKING:
    from butler.gateway.message_handler import ButlerMessageHandler


def _phase_validate_loop_messages(state: LockedTurnState) -> Optional[str]:
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


def _phase_resolve_turn_budget(state: LockedTurnState) -> None:
    state.loop.config, turn_budget, state.augmented = resolve_turn_budget(
        state.augmented, state.loop.config,
    )
    if turn_budget:
        state.health["turn_token_budget"] = turn_budget
        state.health["turn_max_iterations"] = state.loop.config.max_iterations


def _phase_hygiene_compress(
    handler: "ButlerMessageHandler",
    state: LockedTurnState,
) -> None:
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


def _phase_prefetch_and_callbacks(
    handler: "ButlerMessageHandler",
    state: LockedTurnState,
) -> None:
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

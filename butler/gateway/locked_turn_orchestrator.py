"""In-session locked turn orchestrator (ENG-3 / ENG-11)."""

from __future__ import annotations

import logging
import time as _time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from butler.gateway.message_handler import ButlerMessageHandler

logger = logging.getLogger(__name__)


def expand_owner_shortcuts(handler: ButlerMessageHandler, state) -> None:
    """Owner natural-language → slash expansions before normalizers run."""
    from butler.gateway.locked_phases import LockedTurnState
    from butler.gateway.owner_delegate_shortcuts import (
        resolve_project_context,
        try_expand_owner_edit_slash,
    )
    from butler.gateway.owner_ingest_shortcuts import try_expand_owner_ingest_phrase

    assert isinstance(state, LockedTurnState)
    pname, pws = resolve_project_context(handler._orchestrator, state.session_key)
    expanded = try_expand_owner_edit_slash(state.text, project_name=pname)
    if expanded:
        state.text = expanded
        return
    ingest = try_expand_owner_ingest_phrase(
        state.text,
        project_name=pname,
        workspace=pws,
    )
    if ingest:
        state.text = ingest


def run_locked_message_turn(
    handler: ButlerMessageHandler,
    text: str,
    *,
    session_key: str = "default",
    platform: str = "unknown",
    external_id: str | None = None,
) -> str:
    """Execute the in-session pipeline under the per-session lock."""
    from butler.gateway.handler_helpers import _maybe_welcome_prefix
    from butler.gateway.locked_phase_registry import (
        run_augment_phase,
        run_in_context_phases,
        run_pre_lock_phases,
    )
    from butler.gateway.locked_phases import LockedTurnState, _phase_format_error_card
    from butler.execution_context import use_execution_context

    if not text.strip():
        return ""

    state = LockedTurnState(
        text=text,
        session_key=session_key,
        platform=platform,
        external_id=external_id,
    )
    welcome_prefix = _maybe_welcome_prefix(session_key, text)

    expand_owner_shortcuts(handler, state)

    response = run_pre_lock_phases(handler, state)
    if response is not None:
        return response

    state.turn_started = _time.monotonic()
    logger.info(
        "Gateway turn start session=%s platform=%s preview=%r",
        session_key,
        platform,
        text[:80],
    )

    with use_execution_context(handler._orchestrator, session_key=session_key):
        run_augment_phase(handler, state)
        state.loop = handler._get_or_create_loop(session_key)
        state.original_loop_config = state.loop.config
        try:
            response = run_in_context_phases(
                handler, state, welcome_prefix=welcome_prefix,
            )
            if response is not None:
                return response
            return state.out
        except Exception as exc:
            state.health["error"] = str(exc)
            handler._session_registry.set_health(session_key, state.health)
            logger.error(
                "Message handling failed session=%s elapsed=%.1fs: %s",
                session_key,
                _time.monotonic() - state.turn_started,
                exc,
                exc_info=True,
            )
            card = _phase_format_error_card(exc, _time.monotonic() - state.turn_started)
            from butler.gateway.user_errors import format_gateway_user_error

            return card or format_gateway_user_error(exc)
        finally:
            state.loop.config = state.original_loop_config


__all__ = ["expand_owner_shortcuts", "run_locked_message_turn"]

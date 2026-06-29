"""In-session locked turn orchestrator (ENG-3 — extracted from message_handler)."""

from __future__ import annotations

import logging
import time as _time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from butler.gateway.message_handler import ButlerMessageHandler

from butler.gateway.locked_phases import (
    LockedTurnState,
    _phase_apply_correction_intent,
    _phase_apply_github_issues_intent,
    _phase_apply_normalizers_and_slash,
    _phase_apply_prompt_hooks,
    _phase_augment_prompt,
    _phase_execute_turn,
    _phase_finalize_turn,
    _phase_format_error_card,
    _phase_format_turn_response,
    _phase_hygiene_compress,
    _phase_init_loop_role,
    _phase_prefetch_and_callbacks,
    _phase_resolve_turn_budget,
    _phase_validate_loop_messages,
)

logger = logging.getLogger(__name__)


def expand_owner_shortcuts(handler: ButlerMessageHandler, state: LockedTurnState) -> None:
    """Owner natural-language → slash expansions before normalizers run."""
    from butler.gateway.owner_delegate_shortcuts import (
        resolve_project_context,
        try_expand_owner_edit_slash,
    )
    from butler.gateway.owner_ingest_shortcuts import try_expand_owner_ingest_phrase

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
    if not text.strip():
        return ""

    from butler.gateway.handler_helpers import _maybe_welcome_prefix

    state = LockedTurnState(
        text=text,
        session_key=session_key,
        platform=platform,
        external_id=external_id,
    )
    welcome_prefix = _maybe_welcome_prefix(session_key, text)

    expand_owner_shortcuts(handler, state)

    response = _phase_apply_normalizers_and_slash(handler, state)
    if response is not None:
        return response

    response = _phase_apply_correction_intent(handler, state)
    if response is not None:
        return response

    response = _phase_apply_github_issues_intent(handler, state)
    if response is not None:
        from butler.gateway.gateway_transcript import record_gateway_tool_action

        record_gateway_tool_action(
            state.session_key,
            tool_name="mcp_github_lst_repo_issues",
            args_preview=state.text.strip()[:400],
        )
        return response

    _phase_init_loop_role(handler, state)
    state.turn_started = _time.monotonic()
    logger.info(
        "Gateway turn start session=%s platform=%s preview=%r",
        session_key,
        platform,
        text[:80],
    )

    response = _phase_apply_prompt_hooks(state)
    if response is not None:
        return response

    from butler.execution_context import use_execution_context

    with use_execution_context(handler._orchestrator, session_key=session_key):
        _phase_augment_prompt(handler, state)
        state.loop = handler._get_or_create_loop(session_key)
        state.original_loop_config = state.loop.config
        try:
            response = _phase_validate_loop_messages(state)
            if response is not None:
                return response
            _phase_resolve_turn_budget(state)
            _phase_hygiene_compress(handler, state)
            _phase_prefetch_and_callbacks(handler, state)
            _phase_execute_turn(state)
            _phase_finalize_turn(handler, state)
            _phase_format_turn_response(handler, state, welcome_prefix=welcome_prefix)
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

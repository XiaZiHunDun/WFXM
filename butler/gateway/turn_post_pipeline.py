"""Post-inbound-pipeline turn routing (ENG-3).

Runs after ``gateway_inbound_guard`` and the declarative
``inbound_pipeline`` steps: idempotency, queue, admission, session lock,
locked turn, queue drain.
"""

from __future__ import annotations

import logging
import time as _time
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from butler.gateway.message_handler import ButlerMessageHandler

logger = logging.getLogger(__name__)


def run_turn_post_inbound_pipeline(
    handler: ButlerMessageHandler,
    text: str,
    *,
    session_key: str | None,
    platform: str,
    external_id: str | None,
    t0: float,
) -> str:
    """Session routing after inbound pipeline transforms (R1-6 / ENG-3)."""
    from butler.gateway.inbound_pipeline import InboundTurnContext, run_inbound_pipeline
    from butler.gateway.message_pipelines import (
        _phase_apply_admission,
        _phase_apply_idempotency,
        _phase_apply_queue_inbound,
        _phase_apply_session_initializing,
        queue_inbound_for_admission_failure,
    )

    pipeline_ctx = InboundTurnContext(
        handler=handler,
        text=text,
        session_key=session_key,
        platform=platform,
        external_id=external_id,
    )
    pipeline_result = run_inbound_pipeline(handler._inbound_pipeline, pipeline_ctx)
    if pipeline_result.blocked:
        if pipeline_result.block_reply == "drop":
            return ""
        return cast(str, pipeline_result.block_reply)
    text = pipeline_result.text

    from butler.gateway.turn_post_pipeline_ops import record_post_feedback_retry_safe

    record_post_feedback_retry_safe(text, session_key=session_key)

    from butler.gateway.handler_helpers import _is_sessionless_command

    if _is_sessionless_command(text):
        out = handler._handle_message_locked(
            text,
            session_key=session_key,
            platform=platform,
            external_id=external_id,
        )
        logger.info(
            "Gateway handle_message done (slash) session=%s elapsed=%.1fs out_len=%d",
            session_key,
            _time.monotonic() - t0,
            len(out or ""),
        )
        return cast(str, out)

    idem_reply, idempotency_reserved, idempotency_inbound_id = _phase_apply_idempotency(
        text, session_key, external_id=external_id,
    )
    if idem_reply is not None:
        return cast(str, idem_reply)

    block = _phase_apply_session_initializing(
        text,
        session_key,
        platform=platform,
        external_id=external_id,
        orchestrator=handler._orchestrator,
    )
    if block is not None:
        return cast(str, block)

    block = _phase_apply_queue_inbound(
        text, session_key, platform=platform, external_id=external_id, handler=handler,
    )
    if block is not None:
        return cast(str, block)

    admission = _phase_apply_admission(text, session_key)
    if admission is None:
        return cast(
            str,
            queue_inbound_for_admission_failure(
                text, session_key, platform=platform, external_id=external_id,
            ),
        )

    logger.info("Gateway enter_session session=%s", session_key)
    session_lock = handler._session_registry.enter_session(session_key)
    out = ""
    try:
        out = handler._handle_message_locked(
            text,
            session_key=session_key,
            platform=platform,
            external_id=external_id,
        )
        logger.info(
            "Gateway handle_message done session=%s elapsed=%.1fs out_len=%d",
            session_key,
            _time.monotonic() - t0,
            len(out or ""),
        )
    finally:
        handler._session_registry.exit_session(session_key, session_lock)
        from butler.gateway.reply_admission import release

        release(admission)
        if idempotency_reserved:
            from butler.gateway.turn_post_pipeline_ops import complete_inbound_safe

            complete_inbound_safe(session_key, idempotency_inbound_id)
    follow = handler._drain_queued_inbound(
        session_key,
        platform=platform,
        external_id=external_id,
        primary_reply=out,
    )
    if follow:
        out = f"{out}\n\n---\n\n{follow}" if out else follow
    return cast(str, out)


__all__ = ["run_turn_post_inbound_pipeline"]

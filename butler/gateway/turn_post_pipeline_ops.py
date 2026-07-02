"""Best-effort turn post-pipeline side effects (P0-A)."""

from __future__ import annotations

import logging

from butler.core.best_effort import safe_best_effort

logger = logging.getLogger(__name__)


def record_post_feedback_retry_safe(text: str, *, session_key: str | None) -> None:
    def _run() -> None:
        from butler.ops.owner_pmf_metrics import maybe_record_post_feedback_retry

        maybe_record_post_feedback_retry(text, session_key=session_key)

    safe_best_effort(_run, label="turn_post_pipeline.post_feedback_retry", default=None)


def complete_inbound_safe(session_key: str | None, inbound_id: str) -> None:
    try:
        from butler.gateway.inbound_idempotency import complete_inbound

        complete_inbound(session_key, inbound_id)
    except Exception as exc:
        logger.warning(
            "Inbound completion record failed (idempotency may leak): %s",
            exc,
        )

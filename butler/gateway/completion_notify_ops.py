"""Completion notify best-effort helpers (P0-A)."""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)


def outbox_diagnostic_lines_safe(chat_id: str) -> list[str]:
    def _run() -> list[str]:
        from butler.gateway.durable_outbox import outbox_counts

        counts = outbox_counts(chat_id=chat_id)
        if not any(counts.values()):
            return []
        return [
            "出站留痕: "
            f"pending={counts['pending']} sent={counts['sent']} failed={counts['failed']}"
        ]

    from butler.core.best_effort import safe_best_effort

    result = safe_best_effort(
        _run,
        label="completion_notify.outbox_counts",
        default=[],
    )
    return list(result) if isinstance(result, list) else []


async def deliver_completion_push_safe(
    send_fn: Callable[[], Awaitable[Any]],
    *,
    on_success: Callable[[], Awaitable[None] | None],
    on_failure: Callable[[Exception], None],
    kind: str,
) -> bool:
    try:
        result = await send_fn()
        err = getattr(result, "error", None)
        success = getattr(result, "success", True)
        if success is False or err:
            raise RuntimeError(str(err or "send failed"))
        outcome = on_success()
        if outcome is not None:
            await outcome
        return True
    except Exception as exc:
        logger.warning("Gateway completion push failed kind=%s: %s", kind, exc)
        on_failure(exc)
        return False

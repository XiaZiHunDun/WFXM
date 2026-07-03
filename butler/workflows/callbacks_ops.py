"""Workflow callback handler best-effort helpers (P0-A)."""

from __future__ import annotations

import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)


def run_notify_handler_safe(
    *,
    run: Callable[[], None],
) -> None:
    try:
        run()
    except Exception as exc:
        logger.debug("workflow notify handler: %s", exc)


def run_workflow_handler_safe(
    typ: str,
    fn: Callable[[str, Any], None],
    *,
    event: str,
    ctx: Any,
) -> None:
    try:
        fn(event, ctx)
    except Exception as exc:
        logger.warning("workflow handler %s failed: %s", typ, exc)

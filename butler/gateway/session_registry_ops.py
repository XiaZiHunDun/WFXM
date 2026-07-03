"""Gateway session registry best-effort helpers (P0-A)."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from butler.core.best_effort import safe_best_effort

logger = logging.getLogger(__name__)


def publish_session_gauges_safe(*, session_count: int, active_turns: int) -> None:
    def _run() -> None:
        from butler.ops.runtime_metrics import publish_gateway_session_gauges

        publish_gateway_session_gauges(
            session_count=session_count,
            active_turns=active_turns,
        )

    safe_best_effort(_run, label="session_registry.publish_gauges", default=None)


def run_evict_notify_hook_safe(hook: Callable[[str], None], session_key: str) -> None:
    def _run() -> None:
        hook(session_key)

    safe_best_effort(_run, label="session_registry.evict_notify", default=None)


def notify_session_removed_safe(
    callback: Callable[[str], None] | None,
    session_key: str,
) -> None:
    if callback is None:
        return
    try:
        callback(str(session_key or "default"))
    except Exception:
        return

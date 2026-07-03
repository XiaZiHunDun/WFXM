"""Delegate progress heartbeat helpers (P0-A)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from butler.core.best_effort import safe_best_effort

if TYPE_CHECKING:
    from butler.runtime.delegate_job import DelegateJob

logger = logging.getLogger(__name__)


def delegate_iteration_safe(job: "DelegateJob") -> int:
    def _run() -> int:
        loop = job.agent
        return int(getattr(loop, "iteration", 0) or getattr(loop, "_iteration", 0) or 0)

    result = safe_best_effort(_run, label="delegate_progress.iteration", default=0)
    return int(result or 0)


def push_progress_async_safe(job: "DelegateJob", text: str) -> bool:
    import asyncio

    from butler.gateway.completion_notify import deliver_completion_push

    if job.push_target is None or job.push_target.loop is None:
        return False

    async def _send() -> None:
        await deliver_completion_push(
            job.push_target.adapter,
            job.push_target.chat_id,
            text,
            kind="delegate_progress",
        )

    try:
        asyncio.run_coroutine_threadsafe(_send(), job.push_target.loop)
        return True
    except Exception as exc:
        logger.debug("delegate progress async push skipped: %s", exc)
        return False


def push_progress_runtime_safe(text: str) -> None:
    def _run() -> None:
        from butler.runtime.notify import push_runtime_message

        push_runtime_message("[Butler] 委派进度", text)

    safe_best_effort(_run, label="delegate_progress.runtime_push", default=None)


def delegate_progress_notify_enabled_safe() -> bool:
    def _run() -> bool:
        from butler.gateway.completion_notify import delegate_progress_notify_enabled

        return bool(delegate_progress_notify_enabled())

    result = safe_best_effort(_run, label="delegate_progress.enabled", default=False)
    return bool(result)


def heartbeat_push_safe(job: "DelegateJob", text: str) -> None:
    def _run() -> None:
        from butler.runtime.delegate_progress import _push_progress

        _push_progress(job, text)

    safe_best_effort(_run, label="delegate_progress.heartbeat", default=None)

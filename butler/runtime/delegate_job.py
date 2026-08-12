"""Background and foreground delegate execution."""

from __future__ import annotations

import logging
from typing import Any

from butler.core.best_effort import safe_best_effort
from butler.gateway.completion_notify import (
    build_report_push_text,
    delegate_completion_enabled,
    deliver_completion_push,
)
from butler.runtime.delegate_job_body import run_delegate_job_body
from butler.runtime.delegate_job_finalize import (
    run_delegate_job_inner_guarded,
)
from butler.runtime.delegate_progress import delegate_progress_heartbeat
from butler.runtime.notify import push_runtime_message
from butler.runtime.delegate_job_types import DelegateJob, DelegatePushTarget

logger = logging.getLogger(__name__)


def push_delegate_completion(
    report: Any,
    *,
    bridge: Any | None = None,
    push_target: DelegatePushTarget | None = None,
    use_async_push: bool = False,
) -> bool:
    """WeChat notify when a delegate finishes (sync or background)."""
    if not delegate_completion_enabled():
        return False

    prefix = "📋 委派已完成（后台）" if use_async_push else "📋 委派阶段完成"
    text = build_report_push_text(report, prefix=prefix)

    if push_target is not None and push_target.loop is not None:
        import asyncio

        async def _send() -> None:
            await deliver_completion_push(
                push_target.adapter,
                push_target.chat_id,
                text,
                kind="delegate",
            )

        def _schedule() -> bool:
            asyncio.run_coroutine_threadsafe(_send(), push_target.loop)
            return True

        if safe_best_effort(
            _schedule,
            label="delegate_job.async_push_schedule",
            default=False,
        ):
            return True

    if bridge is not None and not use_async_push:

        def _notify() -> bool:
            bridge.notify_delegate_finished(report)
            return True

        if safe_best_effort(_notify, label="delegate_job.bridge_notify", default=False):
            return True

    def _runtime_push() -> bool:
        return bool(push_runtime_message("[Butler] 委派完成", text))

    return bool(
        safe_best_effort(_runtime_push, label="delegate_job.runtime_push", default=False)
    )


def run_delegate_job(job: DelegateJob) -> None:
    """Execute delegate agent loop (intended for background thread)."""
    with delegate_progress_heartbeat(job):
        _run_delegate_job_inner(job)


def _run_delegate_job_inner(job: DelegateJob) -> None:
    run_delegate_job_inner_guarded(job, run_delegate_job_body)

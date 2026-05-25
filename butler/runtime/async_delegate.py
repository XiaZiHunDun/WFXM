"""Schedule delegate_task in a background thread (OpenCode background task subset)."""

from __future__ import annotations

import logging
import threading
from typing import Any

from butler.env_parse import env_truthy
from butler.runtime.delegate_job import DelegateJob, run_delegate_job

logger = logging.getLogger(__name__)

_THREADS: dict[str, threading.Thread] = {}
_LOCK = threading.Lock()


def delegate_async_enabled() -> bool:
    return env_truthy("BUTLER_DELEGATE_ASYNC", default=True)


def should_delegate_async(
    *,
    bridge: Any | None,
    depth: int = 0,
    category_meta: dict[str, Any] | None = None,
) -> bool:
    """Background delegate only for top-level gateway turns with outbound bridge."""
    if depth > 0:
        return False
    if not delegate_async_enabled():
        return False
    meta = category_meta if isinstance(category_meta, dict) else {}
    if meta.get("background") is False:
        return False
    if meta.get("background") is True and bridge is None:
        return False
    return bridge is not None


def push_target_from_bridge(bridge: Any) -> Any:
    from butler.runtime.delegate_job import DelegatePushTarget

    return DelegatePushTarget(
        adapter=bridge.adapter,
        chat_id=str(bridge.chat_id or ""),
        loop=bridge.loop,
    )


def schedule_background_delegate(job: DelegateJob) -> None:
    """Start daemon thread; captures adapter/chat_id for post-close WeChat push."""
    job.use_async_push = True
    if job.bridge is not None and job.push_target is None:
        job.push_target = push_target_from_bridge(job.bridge)

    try:
        from butler.runtime.task_store import update_task

        update_task(job.task_id, background=True)
    except Exception:
        pass

    def _worker() -> None:
        try:
            run_delegate_job(job)
        finally:
            with _LOCK:
                _THREADS.pop(job.task_id, None)

    thread = threading.Thread(
        target=_worker,
        name=f"delegate-{job.task_id}",
        daemon=True,
    )
    with _LOCK:
        _THREADS[job.task_id] = thread
    thread.start()
    logger.info(
        "Scheduled background delegate task_id=%s child=%s",
        job.task_id,
        job.child_session_key,
    )


def is_delegate_running(task_id: str) -> bool:
    with _LOCK:
        t = _THREADS.get(task_id)
    return t is not None and t.is_alive()

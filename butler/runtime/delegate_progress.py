"""Background delegate progress pushes to WeChat (PROD-P3-02)."""

from __future__ import annotations

import logging
import threading
import time
from contextlib import contextmanager
from typing import TYPE_CHECKING, Iterator

if TYPE_CHECKING:
    from butler.runtime.delegate_job import DelegateJob

logger = logging.getLogger(__name__)


def _progress_interval_seconds() -> float:
    try:
        from butler.env_parse import float_env

        return max(45.0, float_env("BUTLER_GATEWAY_DELEGATE_PROGRESS_SECONDS", 90))
    except ValueError:
        return 90.0


def _progress_max_pushes() -> int:
    try:
        from butler.env_parse import int_env

        return int_env("BUTLER_GATEWAY_DELEGATE_PROGRESS_MAX", 5, min=1, max=12)
    except ValueError:
        return 5


def _format_progress_line(job: "DelegateJob", *, elapsed: int, n: int) -> str:
    from butler.runtime.delegate_progress_ops import delegate_iteration_safe
    from butler.runtime.delegate_job import _delegate_role_label

    role = _delegate_role_label(job.role)
    iteration = delegate_iteration_safe(job)
    iter_part = f"第 {iteration} 轮 · " if iteration else ""
    return (
        f"⏳ {role}执行中… {iter_part}已用 {elapsed}s"
        f"（{n}/{_progress_max_pushes()} · 可发 /停止 中断）"
    )


def _push_progress(job: "DelegateJob", text: str) -> None:
    from butler.runtime.delegate_progress_ops import (
        push_progress_async_safe,
        push_progress_runtime_safe,
    )

    if job.push_target is not None and job.push_target.loop is not None:
        if push_progress_async_safe(job, text):
            return
    push_progress_runtime_safe(text)


@contextmanager
def delegate_progress_heartbeat(job: "DelegateJob") -> Iterator[None]:
    """Periodic WeChat progress while ``run_delegate_job`` blocks."""
    from butler.runtime.delegate_progress_ops import (
        delegate_progress_notify_enabled_safe,
        heartbeat_push_safe,
    )

    if not delegate_progress_notify_enabled_safe():
        yield
        return

    stop = threading.Event()
    started = time.monotonic()
    push_count = 0

    def _loop() -> None:
        nonlocal push_count
        interval = _progress_interval_seconds()
        while not stop.wait(timeout=interval):
            if push_count >= _progress_max_pushes():
                return
            elapsed = int(time.monotonic() - started)
            push_count += 1
            heartbeat_push_safe(
                job,
                _format_progress_line(job, elapsed=elapsed, n=push_count),
            )

    thread = threading.Thread(
        target=_loop,
        name=f"delegate-progress-{job.task_id}",
        daemon=True,
    )
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join(timeout=2.0)


__all__ = ["delegate_progress_heartbeat"]

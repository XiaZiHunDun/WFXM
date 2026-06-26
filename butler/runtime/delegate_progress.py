"""Background delegate progress pushes to WeChat (PROD-P3-02)."""

from __future__ import annotations

import logging
import threading
import time
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, Iterator

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
    from butler.runtime.delegate_job import _delegate_role_label

    role = _delegate_role_label(job.role)
    iteration = 0
    try:
        loop = job.agent
        iteration = int(getattr(loop, "iteration", 0) or getattr(loop, "_iteration", 0) or 0)
    except Exception:
        pass
    iter_part = f"第 {iteration} 轮 · " if iteration else ""
    return (
        f"⏳ {role}执行中… {iter_part}已用 {elapsed}s"
        f"（{n}/{_progress_max_pushes()} · 可发 /停止 中断）"
    )


def _push_progress(job: "DelegateJob", text: str) -> None:
    from butler.gateway.completion_notify import deliver_completion_push

    if job.push_target is not None and job.push_target.loop is not None:
        import asyncio

        async def _send() -> None:
            await deliver_completion_push(
                job.push_target.adapter,
                job.push_target.chat_id,
                text,
                kind="delegate_progress",
            )

        try:
            asyncio.run_coroutine_threadsafe(_send(), job.push_target.loop)
            return
        except Exception as exc:
            logger.debug("delegate progress async push skipped: %s", exc)
    try:
        from butler.runtime.notify import push_runtime_message

        push_runtime_message("[Butler] 委派进度", text)
    except Exception as exc:
        logger.debug("delegate progress runtime push skipped: %s", exc)


@contextmanager
def delegate_progress_heartbeat(job: "DelegateJob") -> Iterator[None]:
    """Periodic WeChat progress while ``run_delegate_job`` blocks."""
    try:
        from butler.gateway.completion_notify import delegate_progress_notify_enabled
    except Exception:
        yield
        return
    if not delegate_progress_notify_enabled():
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
            try:
                _push_progress(
                    job,
                    _format_progress_line(job, elapsed=elapsed, n=push_count),
                )
            except Exception as exc:
                logger.debug("delegate progress heartbeat: %s", exc)

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

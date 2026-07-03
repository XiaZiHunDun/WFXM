"""Delegate job finalize guard helpers (P0-A)."""

from __future__ import annotations

from typing import Any, Callable

from butler.core.best_effort import safe_best_effort


def run_delegate_job_inner_guarded_ops(
    job: Any,
    body: Callable[[Any], None],
    *,
    on_failure: Callable[[Any, BaseException], None],
    release_slot: Callable[[], None],
) -> None:
    try:
        body(job)
    except Exception as exc:
        on_failure(job, exc)
    finally:
        safe_best_effort(
            release_slot,
            label="delegate_job.release_slot",
            default=None,
        )

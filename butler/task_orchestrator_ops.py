"""Task orchestrator best-effort helpers (P0-A)."""

from __future__ import annotations

import logging
from typing import Any, Callable

from butler.core.best_effort import safe_best_effort

logger = logging.getLogger(__name__)


def on_progress_safe(
    on_progress: Callable[..., None] | None,
    *args: Any,
    **kwargs: Any,
) -> None:
    if on_progress is None:
        return

    def _run() -> None:
        try:
            on_progress(*args, **kwargs)
        except TypeError:
            if len(args) >= 3:
                on_progress(args[0], args[1], args[2])

    safe_best_effort(_run, label="task_orchestrator.on_progress", default=None)


def truncate_child_response_safe(
    *,
    response_text: str,
    report: Any,
    clear_child_transcript: bool,
) -> str:
    def _run() -> str:
        from butler.core.workflow_flags import workflow_clear_child_enabled

        if workflow_clear_child_enabled() or clear_child_transcript:
            return (report.headline or report.summary or response_text)[:2000]
        return response_text

    result = safe_best_effort(_run, label="task_orchestrator.truncate_child", default=response_text)
    return str(result or response_text)


def workflow_max_parallel_safe(*, default: int | None = None) -> int | None:
    def _run() -> int:
        from butler.core.meta_flags import workflow_max_parallel_default

        return int(workflow_max_parallel_default())

    result = safe_best_effort(_run, label="task_orchestrator.max_parallel", default=default)
    return int(result) if isinstance(result, int) else default


async def spawn_agent_loud(
    run: Callable[[], Any],
    *,
    task_id: str,
) -> Any:
    from butler.task_orchestrator import AgentResult

    try:
        return await run()
    except Exception as exc:
        logger.error("Agent [%s] failed: %s", task_id, exc)
        return AgentResult(success=False, error=str(exc))

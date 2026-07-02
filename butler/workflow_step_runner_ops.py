"""Workflow step runner best-effort helpers (P0-A)."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from butler.core.best_effort import safe_best_effort

if TYPE_CHECKING:
    from butler.task_orchestrator import AgentResult, TaskNode

logger = logging.getLogger(__name__)


def interpolate_workflow_task_safe(node: "TaskNode") -> None:
    def _run() -> None:
        from butler.execution_context import get_workflow_var_pool

        pool = get_workflow_var_pool()
        if pool is not None:
            node.config.task = pool.interpolate(node.config.task)

    safe_best_effort(_run, label="workflow_step.interpolate", default=None)


def observe_step_duration_ms_safe(node_id: str, elapsed_ms: float) -> None:
    def _run() -> None:
        from butler.ops.runtime_metrics import observe_ms

        observe_ms(
            "workflow_step_duration_ms",
            elapsed_ms,
            labels={"step": node_id},
        )

    safe_best_effort(_run, label="workflow_step.duration_metric", default=None)


def evaluate_until_assertion_loud(
    node: "TaskNode",
    last_result: "AgentResult",
) -> "AgentResult":
    from butler.task_orchestrator import AgentResult

    try:
        from butler.workflows.until_assert import evaluate_until

        ok, err = evaluate_until(last_result.response or "", node.until)
        if not ok:
            return AgentResult(
                success=False,
                error=err or "until_assertion_failed",
                response=last_result.response,
            )
    except ImportError:
        return last_result
    except Exception as exc:
        logger.error(
            "until assertion raised for step %s — treating as failed: %s",
            node.id,
            exc,
        )
        return AgentResult(
            success=False,
            error=f"until_assertion_error: {exc}",
            response=last_result.response,
        )
    return last_result

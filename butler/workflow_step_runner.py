"""Workflow step retry + rescue helpers extracted from TaskOrchestrator (ENG-4)."""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from butler.task_orchestrator import AgentResult, AgentSpawnConfig, TaskNode

logger = logging.getLogger(__name__)

SpawnFn = Callable[..., Awaitable["AgentResult"]]
ProgressFn = Callable[[str, str, str], None]


def interpolate_workflow_task(node: "TaskNode") -> None:
    try:
        from butler.execution_context import get_workflow_var_pool

        pool = get_workflow_var_pool()
        if pool is not None:
            node.config.task = pool.interpolate(node.config.task)
    except Exception as exc:
        logger.debug("workflow task interpolate skipped: %s", exc)


def _observe_step_duration_ms(node_id: str, elapsed_ms: float) -> None:
    try:
        from butler.ops.runtime_metrics import observe_ms

        observe_ms(
            "workflow_step_duration_ms",
            elapsed_ms,
            labels={"step": node_id},
        )
    except Exception as exc:
        logger.debug("workflow step duration metric skipped: %s", exc)


def _evaluate_until_assertion(
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


async def run_step_with_retry(
    node: "TaskNode",
    *,
    spawn: SpawnFn,
    on_progress: ProgressFn | None = None,
) -> "AgentResult":
    """Run one DAG node with retries and optional until-assertion."""
    from butler.task_orchestrator import AgentResult

    interpolate_workflow_task(node)
    last_result = AgentResult(success=False, error="No attempts")
    for attempt in range(node.max_retries):
        t0 = time.perf_counter()
        last_result = await spawn(node.config, on_progress=on_progress)
        _observe_step_duration_ms(node.id, (time.perf_counter() - t0) * 1000.0)
        if last_result.success:
            checked = _evaluate_until_assertion(node, last_result)
            if not checked.success:
                return checked
            return last_result
        logger.warning(
            "Node %s attempt %d/%d failed",
            node.id,
            attempt + 1,
            node.max_retries,
        )
    if not last_result.success and node.rescue_configs:
        last_result = await run_rescue_steps(
            node,
            last_result,
            spawn=spawn,
            on_progress=on_progress,
        )
    return last_result


async def run_rescue_steps(
    node: "TaskNode",
    failed: "AgentResult",
    *,
    spawn: SpawnFn,
    on_progress: ProgressFn | None = None,
) -> "AgentResult":
    """Ansible-style rescue: run fallback agents after primary failure."""
    from butler.core.workflow_flags import workflow_rescue_enabled
    from butler.task_orchestrator import AgentResult

    if not workflow_rescue_enabled():
        return failed
    parts = [
        (failed.response or "").strip(),
        f"[步骤 {node.id} 失败] {failed.error or 'unknown'}".strip(),
    ]
    for idx, cfg in enumerate(node.rescue_configs):
        rescue_id = f"{node.id}__rescue_{idx}"
        if on_progress:
            try:
                on_progress(rescue_id, "start", cfg.role)
            except Exception as exc:
                logger.debug("rescue on_progress: %s", exc)
        r = await spawn(cfg, on_progress=on_progress)
        if on_progress:
            try:
                on_progress(rescue_id, "done", cfg.role)
            except Exception as exc:
                logger.debug("rescue on_progress done skipped: %s", exc)
        if r.response:
            parts.append(f"## Rescue ({rescue_id})\n{r.response[:3000]}")
    merged = "\n\n".join(p for p in parts if p)
    return AgentResult(
        success=False,
        response=merged,
        report=failed.report,
        error=failed.error or "rescue_completed",
        tokens_used=failed.tokens_used,
        iterations=failed.iterations,
        tool_calls=failed.tool_calls,
        elapsed_seconds=failed.elapsed_seconds,
    )


__all__ = [
    "interpolate_workflow_task",
    "run_rescue_steps",
    "run_step_with_retry",
]

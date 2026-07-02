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
    from butler.workflow_step_runner_ops import interpolate_workflow_task_safe

    interpolate_workflow_task_safe(node)


def _observe_step_duration_ms(node_id: str, elapsed_ms: float) -> None:
    from butler.workflow_step_runner_ops import observe_step_duration_ms_safe

    observe_step_duration_ms_safe(node_id, elapsed_ms)


def _evaluate_until_assertion(
    node: "TaskNode",
    last_result: "AgentResult",
) -> "AgentResult":
    from butler.workflow_step_runner_ops import evaluate_until_assertion_loud

    return evaluate_until_assertion_loud(node, last_result)


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
    from butler.task_orchestrator_ops import on_progress_safe

    if not workflow_rescue_enabled():
        return failed
    parts = [
        (failed.response or "").strip(),
        f"[步骤 {node.id} 失败] {failed.error or 'unknown'}".strip(),
    ]
    for idx, cfg in enumerate(node.rescue_configs):
        rescue_id = f"{node.id}__rescue_{idx}"
        on_progress_safe(on_progress, rescue_id, "start", cfg.role)
        r = await spawn(cfg, on_progress=on_progress)
        on_progress_safe(on_progress, rescue_id, "done", cfg.role)
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

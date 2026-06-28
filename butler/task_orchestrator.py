"""Butler Task Orchestrator — DAG-based multi-agent task execution.

Uses Butler's own AgentLoop for sub-agent spawning. Every sub-agent
goes through Butler's orchestrator, inheriting the correct model
config, memory, skills, and agent profile.

Key improvements over v3:
  - AgentSpawnConfig includes tools and model_config fields
  - AgentResult includes AgentReport and tokens_used
  - Real parallel execution via asyncio.to_thread
  - Sub-agents use Butler profiles and toolsets
"""

from __future__ import annotations

import asyncio
from contextvars import copy_context
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from butler.report import AgentReport, cache_report

logger = logging.getLogger(__name__)
_MODEL_OVERRIDE_LOCK = threading.RLock()


class AgentStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class AgentSpawnConfig:
    """Configuration for spawning a sub-agent."""
    role: str  # dev, content, review
    task: str
    context: str = ""
    tools: list[str] | None = None
    model_config: dict[str, Any] | None = None
    max_iterations: int = 30
    output_format: str = "text"
    project_name: str | None = None
    delegate_depth: int = 0
    session_key: str = ""
    clear_child_transcript: bool = False


@dataclass
class AgentResult:
    """Result from a sub-agent execution, including structured report."""
    success: bool
    response: str = ""
    report: AgentReport | None = None
    tokens_used: int = 0
    iterations: int = 0
    tool_calls: int = 0
    elapsed_seconds: float = 0.0
    error: str = ""
    artifacts: list[str] = field(default_factory=list)


@dataclass
class AgentTask:
    id: str
    config: AgentSpawnConfig
    status: AgentStatus = AgentStatus.PENDING
    result: AgentResult | None = None
    started_at: float = 0.0
    completed_at: float = 0.0


@dataclass
class TaskNode:
    """Node in a task DAG."""
    id: str
    config: AgentSpawnConfig
    depends_on: list[str] = field(default_factory=list)
    # Return a direct dependent id to choose one branch; return None to fan out all dependents.
    router: Callable[[AgentResult], str | None] | None = None
    requires_approval: bool = False
    max_retries: int = 1
    handoff_only: bool = True
    clear_child_transcript: bool = False
    supervisor_note: str = ""
    optional: bool = False
    rescue_configs: list[AgentSpawnConfig] = field(default_factory=list)
    until: dict | None = None


@dataclass
class TaskGraphResult:
    nodes: dict[str, AgentResult] = field(default_factory=dict)
    execution_order: list[str] = field(default_factory=list)
    success: bool = True
    error: str = ""


class TaskOrchestrator:
    """Execute multi-agent workflows using Butler's AgentLoop."""

    def __init__(self) -> None:
        import threading

        self._tasks_lock = threading.Lock()
        self._tasks: dict[str, AgentTask] = {}

    def _create_agent_loop(self, config: AgentSpawnConfig):
        """Create a Butler AgentLoop for the given config."""
        orch = _orchestrator_for_task()

        if config.model_config:
            from butler.config import ModelConfig
            mc = ModelConfig(**config.model_config)
            settings = orch._settings
            with _MODEL_OVERRIDE_LOCK:
                previous = getattr(settings, "_runtime_model_overrides", {}).get(config.role)
                settings.set_runtime_model_override(config.role, mc)
                try:
                    return self._create_agent_loop_with_orchestrator(config, orch)
                finally:
                    settings.set_runtime_model_override(config.role, previous)

        return self._create_agent_loop_with_orchestrator(config, orch)

    def _create_agent_loop_with_orchestrator(self, config: AgentSpawnConfig, orch: Any):
        """Create a Butler AgentLoop using an already-selected orchestrator."""
        from butler.delegate.policy import DELEGATE_BLOCKED_TOOLS
        from butler.tools.project_tools import (
            canonical_tool_name,
            get_tool_definitions_for_project,
        )

        project = orch.project_manager.get_current(session_key=str(config.session_key or ""))
        tools = get_tool_definitions_for_project(project, role=config.role)
        delegated_tools = [
            t for t in tools
            if t["function"]["name"] not in DELEGATE_BLOCKED_TOOLS
        ]

        if config.tools:
            tool_names = {canonical_tool_name(n) for n in config.tools}
            delegated_tools = [
                t for t in delegated_tools
                if t["function"]["name"] in tool_names
            ]

        from butler.core.delegate_context import child_callbacks, get_parent_callbacks

        agent = orch.create_project_agent_loop(
            role=config.role,
            tools=delegated_tools,
            tool_dispatcher=lambda name, args: dispatch_tool_safely(
                name,
                args,
                depth=config.delegate_depth + 1,
            ),
            callbacks=child_callbacks(get_parent_callbacks()),
        )

        agent.config.max_iterations = config.max_iterations
        agent._butler_orchestrator = orch
        return agent

    async def spawn_agent(
        self,
        config: AgentSpawnConfig,
        on_progress: Callable[[str, str, str], None] | None = None,
    ) -> AgentResult:
        """Spawn a Butler AgentLoop and run the task."""
        task_id = uuid.uuid4().hex[:8]
        task = AgentTask(id=task_id, config=config)
        with self._tasks_lock:
            if len(self._tasks) > 200:
                completed = [
                    k for k, v in self._tasks.items()
                    if getattr(v, "status", None) in ("completed", "error", "cancelled")
                ]
                for k in completed[:100]:
                    del self._tasks[k]
            self._tasks[task_id] = task
        task.status = AgentStatus.RUNNING
        task.started_at = time.time()

        logger.info("Spawning %s agent [%s]: %s", config.role, task_id, config.task[:80])

        if on_progress:
            try:
                on_progress(task_id, "start", config.role)
            except Exception as exc:
                logger.debug("on_progress start failed: %s", exc)

        try:
            from butler.delegate.policy import MAX_DELEGATE_DEPTH

            if config.delegate_depth >= MAX_DELEGATE_DEPTH:
                raise ValueError(f"Maximum delegation depth ({MAX_DELEGATE_DEPTH}) exceeded")

            agent = self._create_agent_loop(config)

            raw_user_message = config.task
            if config.context:
                raw_user_message = f"## 上下文\n{config.context}\n\n## 任务\n{config.task}"

            agent.reset()
            orch = getattr(agent, "_butler_orchestrator", None)
            session_key = _resolve_spawn_session_key(config, task_id)
            user_message = raw_user_message
            if orch is not None and hasattr(orch, "inject_skill_context"):
                user_message = orch.inject_skill_context(raw_user_message)
                from butler.session.lifecycle import attach_turn_memory_prefetch

                attach_turn_memory_prefetch(agent, orch, raw_user_message, role=config.role)
            from butler.execution_context import use_execution_context

            with use_execution_context(orch, session_key=session_key):
                run_context = copy_context()
                loop_result = await asyncio.to_thread(
                    run_context.run,
                    agent.run,
                    user_message,
                )
            if orch is not None:
                from butler.session.lifecycle import sync_turn_memory

                sync_turn_memory(
                    orch,
                    raw_user_message,
                    loop_result.final_response or "",
                    interrupted=loop_result.status.value == "interrupted",
                    status=loop_result.status,
                    session_id=session_key,
                )

            from butler.tools.registry import _extract_changes_from_messages
            changes = _extract_changes_from_messages(loop_result.messages)
            report = AgentReport(
                headline=f"{config.role} 代理完成任务",
                summary=loop_result.final_response or "",
                changes=changes,
                success=loop_result.status.value == "completed",
                iterations=loop_result.iterations,
                tool_calls=loop_result.tool_calls_made,
                tokens_used=loop_result.total_tokens,
                elapsed_seconds=loop_result.elapsed_seconds,
            )
            from butler.report import enrich_report_decisions

            enrich_report_decisions(report, loop_result.final_response or "")
            cache_report(report, session_key=session_key)
            success = loop_result.status.value == "completed"

            response_text = loop_result.final_response or ""
            try:
                from butler.core.workflow_flags import workflow_clear_child_enabled

                if workflow_clear_child_enabled() or config.clear_child_transcript:
                    response_text = (
                        report.headline
                        or report.summary
                        or response_text
                    )[:2000]
            except Exception as exc:
                logger.debug("spawn agent skipped: %s", exc)
            result = AgentResult(
                success=success,
                response=response_text,
                report=report,
                tokens_used=loop_result.total_tokens,
                iterations=loop_result.iterations,
                tool_calls=loop_result.tool_calls_made,
                elapsed_seconds=loop_result.elapsed_seconds,
                error="" if success else (loop_result.error or loop_result.status.value),
            )
        except Exception as exc:
            logger.error("Agent [%s] failed: %s", task_id, exc)
            result = AgentResult(success=False, error=str(exc))

        task.completed_at = time.time()
        task.status = AgentStatus.COMPLETED if result.success else AgentStatus.FAILED
        task.result = result

        elapsed = task.completed_at - task.started_at
        logger.info("Agent [%s] %s in %.1fs", task_id, task.status.value, elapsed)

        if on_progress:
            try:
                status_label = "done" if result.success else "failed"
                preview = ""
                if status_label != "start":
                    preview = (result.response or result.error or "")[:500]
                try:
                    on_progress(task_id, status_label, config.role, preview)
                except TypeError:
                    on_progress(task_id, status_label, config.role)
            except Exception as exc:
                logger.debug("on_progress end failed: %s", exc)

        return result

    async def spawn_parallel(self, configs: list[AgentSpawnConfig]) -> list[AgentResult]:
        """Spawn multiple agents in true parallel via asyncio.to_thread."""
        tasks = [self.spawn_agent(cfg) for cfg in configs]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return [_coerce_agent_result(result) for result in results]

    async def spawn_sequential(
        self,
        configs: list[AgentSpawnConfig],
        pass_context: bool = True,
    ) -> list[AgentResult]:
        """Execute agents sequentially, optionally passing context."""
        results: list[AgentResult] = []
        accumulated_context = ""

        for cfg in configs:
            if pass_context and accumulated_context:
                cfg.context = (cfg.context or "") + "\n\n" + accumulated_context

            result = await self.spawn_agent(cfg)
            results.append(result)

            if result.success and result.response:
                accumulated_context += f"\n[{cfg.role} 结果]: {result.response[:2000]}"

            if not result.success:
                logger.warning("Sequential chain broken at role=%s", cfg.role)
                break

        return results

    async def execute_graph(
        self,
        nodes: list[TaskNode],
        on_approval: Callable[[TaskNode], bool] | None = None,
        on_progress: Callable[[str, str, str], None] | None = None,
        *,
        max_parallel: int | None = None,
        serial: bool = False,
    ) -> TaskGraphResult:
        """Execute a DAG of tasks with dependency resolution."""
        from butler.core.meta_flags import MAX_DAG_NODES

        if len(nodes) > MAX_DAG_NODES:
            raise ValueError(
                f"DAG exceeds maximum node count ({len(nodes)} > {MAX_DAG_NODES})"
            )

        graph_result = TaskGraphResult()
        node_map = {n.id: n for n in nodes}
        completed: dict[str, AgentResult] = {}
        cancelled: set[str] = set()
        errors: list[str] = []

        from butler.dag_scheduler import (
            cancel_direct_dependents,
            direct_dependents as list_direct_dependents,
            first_cancelled_dependency,
            first_failed_dependency,
            format_dependency_context,
            graph_all_required_ok,
            group_into_layers,
            topological_sort,
        )

        order = topological_sort(nodes)

        layers = group_into_layers(order, node_map)
        step_index = 0

        try:
            from butler.core.meta_flags import workflow_max_parallel_default

            if max_parallel is None:
                max_parallel = workflow_max_parallel_default()
        except Exception as exc:
            logger.debug("execute graph skipped: %s", exc)
        for layer in layers:
            layer_tasks = []
            for node_id in layer:
                node = node_map[node_id]
                if node_id in completed or node_id in cancelled:
                    continue

                cancelled_dep = first_cancelled_dependency(node, cancelled)
                if cancelled_dep:
                    completed[node_id] = AgentResult(
                        success=False,
                        error=f"Skipped due to cancelled dependency: {cancelled_dep}",
                    )
                    continue

                failed_dep = first_failed_dependency(node, completed, node_map)
                if failed_dep:
                    completed[node_id] = AgentResult(
                        success=False,
                        error=f"Skipped due to failed dependency: {failed_dep}",
                    )
                    continue

                if node.depends_on:
                    dep_contexts = []
                    for dep_id in node.depends_on:
                        dep_result = completed.get(dep_id)
                        if dep_result is None:
                            continue
                        block = format_dependency_context(
                            dep_id,
                            dep_result,
                            handoff_only=node.handoff_only,
                        )
                        if block:
                            dep_contexts.append(block)
                    if dep_contexts:
                        node.config.context = (
                            (node.config.context or "") + "\n\n" + "\n".join(dep_contexts)
                        )

                if node.supervisor_note.strip():
                    sup = f"## Supervisor 指令\n{node.supervisor_note.strip()[:600]}"
                    node.config.context = (
                        (node.config.context or "") + "\n\n" + sup
                    ).strip()

                if node.requires_approval:
                    if on_approval is None or not on_approval(node):
                        completed[node_id] = AgentResult(
                            success=False,
                            error="workflow_step_approval_pending",
                        )
                        continue

                layer_tasks.append((node_id, node))

            if not layer_tasks:
                continue

            if serial:
                batches = [[item] for item in layer_tasks]
            elif max_parallel and max_parallel > 0:
                batches = [
                    layer_tasks[i : i + max_parallel]
                    for i in range(0, len(layer_tasks), max_parallel)
                ]
            else:
                batches = [layer_tasks]

            for batch in batches:
                if len(batch) == 1:
                    nid, node = batch[0]
                    step_index += 1
                    if on_progress:
                        try:
                            on_progress(nid, "start", node.config.role)
                        except Exception as exc:
                            logger.debug("graph on_progress start: %s", exc)
                    from butler.execution_context import use_workflow_step

                    with use_workflow_step(nid):
                        result = _coerce_agent_result(
                            await self._run_with_retry(node, on_progress=on_progress)
                        )
                    completed[nid] = result
                    graph_result.execution_order.append(nid)
                else:
                    from butler.execution_context import use_workflow_step

                    async def _run_one(n: TaskNode) -> AgentResult:
                        with use_workflow_step(n.id):
                            return await self._run_with_retry(n, on_progress=on_progress)

                    parallel_results = await asyncio.gather(
                        *[_run_one(node) for _, node in batch],
                        return_exceptions=True,
                    )
                    for (nid, _), result in zip(batch, parallel_results):
                        completed[nid] = _coerce_agent_result(result)
                        graph_result.execution_order.append(nid)

            for nid in [lid for lid, _ in layer_tasks]:
                node = node_map[nid]
                result = completed[nid]
                if node.router and result.success:
                    try:
                        next_id = node.router(result)
                    except Exception as exc:
                        errors.append(f"Router for {nid!r} failed: {exc}")
                        cancel_direct_dependents(node_map, nid, cancelled)
                        continue
                    if not next_id:
                        continue
                    if next_id not in node_map:
                        errors.append(f"Router for {nid!r} returned unknown target {next_id!r}")
                        cancel_direct_dependents(node_map, nid, cancelled)
                        continue
                    deps = list_direct_dependents(node_map, nid)
                    if next_id not in {dependent.id for dependent in deps}:
                        errors.append(
                            f"Router for {nid!r} returned non-direct dependent {next_id!r}"
                        )
                        cancel_direct_dependents(node_map, nid, cancelled)
                        continue
                    for dependent in deps:
                        if dependent.id != next_id:
                            cancelled.add(dependent.id)

        for node_id in order:
            if node_id in completed or node_id in cancelled:
                continue
            cancelled_dep = first_cancelled_dependency(node_map[node_id], cancelled)
            if cancelled_dep:
                completed[node_id] = AgentResult(
                    success=False,
                    error=f"Skipped due to cancelled dependency: {cancelled_dep}",
                )
            else:
                errors.append(f"Node {node_id!r} was not executed")

        graph_result.nodes = completed
        graph_result.error = "; ".join(errors)
        graph_result.success = (
            not errors and graph_all_required_ok(completed, node_map)
        )
        return graph_result

    async def _run_with_retry(
        self,
        node: TaskNode,
        on_progress: Callable[[str, str, str], None] | None = None,
    ) -> AgentResult:
        import time as _time

        try:
            from butler.execution_context import get_workflow_var_pool

            pool = get_workflow_var_pool()
            if pool is not None:
                node.config.task = pool.interpolate(node.config.task)  # type: ignore[attr-defined]
        except Exception as exc:
            logger.debug("run with retry skipped: %s", exc)
        last_result = AgentResult(success=False, error="No attempts")
        for attempt in range(node.max_retries):
            t0 = _time.perf_counter()
            last_result = await self.spawn_agent(node.config, on_progress=on_progress)
            try:
                from butler.ops.runtime_metrics import observe_ms

                observe_ms(
                    "workflow_step_duration_ms",
                    (_time.perf_counter() - t0) * 1000.0,
                    labels={"step": node.id},
                )
            except Exception as exc:
                logger.debug("run with retry skipped: %s", exc)
            if last_result.success:
                try:
                    from butler.workflows.until_assert import evaluate_until

                    ok, err = evaluate_until(
                        last_result.response or "",
                        node.until,
                    )
                    if not ok:
                        last_result = AgentResult(
                            success=False,
                            error=err or "until_assertion_failed",
                            response=last_result.response,
                        )
                        return last_result
                except ImportError:
                    pass
                except Exception as exc:
                    logger.error("until assertion raised for step %s — treating as failed: %s", node.id, exc)
                    last_result = AgentResult(
                        success=False,
                        error=f"until_assertion_error: {exc}",
                        response=last_result.response,
                    )
                    return last_result
                return last_result
            logger.warning(
                "Node %s attempt %d/%d failed",
                node.id, attempt + 1, node.max_retries,
            )
        if not last_result.success and node.rescue_configs:
            last_result = await self._run_rescue_steps(
                node,
                last_result,
                on_progress=on_progress,
            )
        return last_result

    async def _run_rescue_steps(
        self,
        node: TaskNode,
        failed: AgentResult,
        *,
        on_progress: Callable[[str, str, str], None] | None = None,
    ) -> AgentResult:
        from butler.core.workflow_flags import workflow_rescue_enabled

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
            r = await self.spawn_agent(cfg, on_progress=on_progress)
            if on_progress:
                try:
                    on_progress(rescue_id, "done", cfg.role)
                except Exception as exc:
                    logger.debug("run rescue steps skipped: %s", exc)
            if r.response:
                parts.append(f"## Rescue ({rescue_id})\n{r.response[:3000]}")
        merged = "\n\n".join(p for p in parts if p)
        # Rescue intentionally keeps success=False (Ansible "rescued" semantics):
        # downstream steps see it as failed; rescue output is preserved for diagnostics.
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


def _resolve_spawn_session_key(config: AgentSpawnConfig, task_id: str) -> str:
    """Pick a stable audit/session key for orchestrator spawns."""
    explicit = str(config.session_key or "").strip()
    if explicit:
        return explicit
    from butler.execution_context import get_current_session_key

    inherited = str(get_current_session_key() or "").strip()
    if inherited:
        return inherited
    return f"task:{task_id}"


def _orchestrator_for_task():
    from butler.execution_context import get_current_orchestrator

    orch = get_current_orchestrator()
    if orch is not None:
        return orch

    from butler.orchestrator import ButlerOrchestrator

    return ButlerOrchestrator(user_id="owner", channel="orchestrator")


def dispatch_tool_safely(name: str, args: dict, *, depth: int) -> str:
    """Dispatch a tool call with delegate depth propagated consistently."""
    from butler.tools.registry import _safe_dispatch

    return _safe_dispatch(name, args, depth)


def _coerce_agent_result(result: AgentResult | BaseException) -> AgentResult:
    if isinstance(result, AgentResult):
        return result
    return AgentResult(success=False, error=str(result))

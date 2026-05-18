"""SubAgent orchestration engine - manages agent spawning, lifecycle, and results.

Replaces the minimal TaskOrchestrator with a full SubAgent orchestration system.
Agents are spawned with explicit configs, budgets, and context; results are
structured and can be aggregated.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable

from butler.config.settings import ModelConfig

logger = logging.getLogger(__name__)


class AgentStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    WAITING_APPROVAL = "waiting_approval"


@dataclass
class AgentSpawnConfig:
    """Everything needed to spawn a SubAgent."""
    role: str
    task: str
    tools: list[str] = field(default_factory=list)
    model_config: ModelConfig = field(default_factory=ModelConfig)
    max_turns: int = 30
    context: str = ""
    output_format: str = ""
    project_name: str = ""


@dataclass
class AgentResult:
    """Structured output from a completed SubAgent."""
    success: bool = True
    response: str = ""
    summary: str = ""
    artifacts: list[str] = field(default_factory=list)
    turns_used: int = 0
    tokens_used: dict[str, int] = field(default_factory=lambda: {"input": 0, "output": 0})
    error: str = ""


@dataclass
class AgentTask:
    """Tracks a running or completed agent task."""
    id: str
    config: AgentSpawnConfig
    status: AgentStatus = AgentStatus.PENDING
    result: AgentResult | None = None
    started_at: float = 0.0
    completed_at: float = 0.0


@dataclass
class TaskNode:
    """A node in a task execution graph."""
    id: str
    config: AgentSpawnConfig
    depends_on: list[str] = field(default_factory=list)
    router: Callable[[AgentResult], str] | None = None  # returns next node id
    requires_approval: bool = False
    retry_count: int = 0
    max_retries: int = 1


@dataclass
class TaskGraphResult:
    """Result of executing a task graph."""
    success: bool = True
    node_results: dict[str, AgentResult] = field(default_factory=dict)
    execution_order: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    waiting_approval: str = ""  # node_id waiting for approval, empty if none


class TaskOrchestrator:
    """Manages SubAgent lifecycle: spawn, track, aggregate results."""

    def __init__(self):
        self._tasks: dict[str, AgentTask] = {}
        self._on_progress: dict[str, Callable] = {}
        self._checkpoints: dict[str, dict[str, AgentResult]] = {}

    async def spawn_agent(
        self,
        config: AgentSpawnConfig,
        on_progress: Callable[[int, str, str], None] | None = None,
    ) -> AgentResult:
        """Spawn a SubAgent and wait for its completion."""
        task_id = str(uuid.uuid4())[:8]
        task = AgentTask(id=task_id, config=config)
        self._tasks[task_id] = task

        from butler.executors.agent_profiles import get_profile
        from butler.executors.agent_runner import AgentRunner

        profile = get_profile(config.role)
        if profile is None:
            task.status = AgentStatus.FAILED
            result = AgentResult(success=False, error=f"Unknown agent role: {config.role}")
            task.result = result
            return result

        tools = config.tools or profile.tools
        system_prompt = profile.system_prompt

        model_config = config.model_config
        if model_config.is_empty():
            from butler.core.project_manager import project_manager
            proj = project_manager.get_project(config.project_name) if config.project_name else project_manager.get_current()
            if proj:
                model_config = proj.resolve_model(config.role)
            else:
                from butler.config.settings import settings
                model_config = settings.get_model_config(config.role)

        runner = AgentRunner(
            model_config=model_config,
            tools=tools,
            system_prompt=system_prompt,
            max_turns=config.max_turns,
        )

        task.status = AgentStatus.RUNNING
        task.started_at = time.time()
        logger.info(f"Spawning {config.role} agent [{task_id}]: {config.task[:80]}")

        runner_result = await runner.run(
            task=config.task,
            context=config.context,
            on_turn=on_progress,
        )

        task.completed_at = time.time()
        result = AgentResult(
            success=runner_result.success,
            response=runner_result.response,
            artifacts=runner_result.artifacts,
            turns_used=runner_result.turns_used,
            tokens_used=runner_result.tokens_used,
            error=runner_result.error,
        )

        task.status = AgentStatus.COMPLETED if result.success else AgentStatus.FAILED
        task.result = result

        elapsed = task.completed_at - task.started_at
        logger.info(
            f"Agent [{task_id}] {task.status.value} in {elapsed:.1f}s, "
            f"{result.turns_used} turns, {sum(result.tokens_used.values())} tokens"
        )

        return result

    async def spawn_background(
        self,
        config: AgentSpawnConfig,
        on_complete: Callable[[AgentResult], Any] | None = None,
    ) -> str:
        """Spawn an agent in background and return its task ID."""
        task_id = str(uuid.uuid4())[:8]
        task = AgentTask(id=task_id, config=config)
        self._tasks[task_id] = task

        async def _run():
            result = await self.spawn_agent(config)
            if on_complete:
                if asyncio.iscoroutinefunction(on_complete):
                    await on_complete(result)
                else:
                    on_complete(result)

        asyncio.create_task(_run())
        return task_id

    async def spawn_parallel(
        self,
        configs: list[AgentSpawnConfig],
    ) -> list[AgentResult]:
        """Spawn multiple agents in parallel and collect all results."""
        tasks = [self.spawn_agent(cfg) for cfg in configs]
        return await asyncio.gather(*tasks, return_exceptions=False)

    async def spawn_sequential(
        self,
        configs: list[AgentSpawnConfig],
        pass_context: bool = True,
    ) -> list[AgentResult]:
        """Spawn agents sequentially. If pass_context is True, each agent
        receives the previous agent's response as additional context."""
        results: list[AgentResult] = []
        accumulated_context = ""
        for cfg in configs:
            if pass_context and accumulated_context:
                cfg.context = (cfg.context + "\n\n前序 Agent 的输出:\n" + accumulated_context).strip()
            result = await self.spawn_agent(cfg)
            results.append(result)
            if result.success:
                accumulated_context = result.response[:2000]
            else:
                break
        return results

    def get_task(self, task_id: str) -> AgentTask | None:
        return self._tasks.get(task_id)

    def list_tasks(
        self,
        project: str = "",
        status: AgentStatus | None = None,
    ) -> list[AgentTask]:
        tasks = list(self._tasks.values())
        if project:
            tasks = [t for t in tasks if t.config.project_name == project]
        if status:
            tasks = [t for t in tasks if t.status == status]
        return sorted(tasks, key=lambda t: t.started_at, reverse=True)

    def clear_completed(self) -> int:
        completed_ids = [tid for tid, t in self._tasks.items() if t.status in (AgentStatus.COMPLETED, AgentStatus.FAILED)]
        for tid in completed_ids:
            del self._tasks[tid]
        return len(completed_ids)

    def _topological_sort(self, nodes: list[TaskNode]) -> list[list[str]]:
        """Returns layers of node IDs that can be executed in parallel."""
        node_ids = {n.id for n in nodes}
        in_deg: dict[str, int] = {nid: 0 for nid in node_ids}
        children: dict[str, list[str]] = {nid: [] for nid in node_ids}

        for n in nodes:
            inc = sum(1 for d in n.depends_on if d in node_ids)
            in_deg[n.id] = inc
            for d in n.depends_on:
                if d in node_ids:
                    children[d].append(n.id)

        layers: list[list[str]] = []
        current = sorted(nid for nid in node_ids if in_deg[nid] == 0)

        while current:
            layers.append(list(current))
            nxt: list[str] = []
            for u in current:
                for v in children[u]:
                    in_deg[v] -= 1
                    if in_deg[v] == 0:
                        nxt.append(v)
            current = sorted(nxt)

        total = sum(len(L) for L in layers)
        if total != len(node_ids):
            return []
        return layers

    def _direct_dependents(self, node_map: dict[str, TaskNode], parent_id: str) -> list[TaskNode]:
        return [n for n in node_map.values() if parent_id in n.depends_on]

    def _apply_router_cancellations(
        self,
        node_map: dict[str, TaskNode],
        parent: TaskNode,
        parent_result: AgentResult,
        cancelled: set[str],
        errors: list[str],
    ) -> None:
        if not parent.router:
            return
        try:
            nxt = parent.router(parent_result)
        except Exception as e:
            errors.append(f"router error for node {parent.id}: {e}")
            return
        if not nxt:
            return
        direct = self._direct_dependents(node_map, parent.id)
        ids = {d.id for d in direct}
        if nxt not in ids:
            errors.append(f"router for {parent.id} returned unknown successor {nxt!r}")
            return
        for d in direct:
            if d.id != nxt:
                cancelled.add(d.id)

    def _propagate_dependency_failures(
        self,
        node_map: dict[str, TaskNode],
        failed_id: str,
        cancelled: set[str],
    ) -> None:
        stack = list(self._direct_dependents(node_map, failed_id))
        seen: set[str] = set(cancelled)
        while stack:
            n = stack.pop()
            if n.id in seen:
                continue
            seen.add(n.id)
            cancelled.add(n.id)
            stack.extend(self._direct_dependents(node_map, n.id))

    def _node_deps_satisfied_for_graph(
        self,
        nid: str,
        node_map: dict[str, TaskNode],
        node_results: dict[str, AgentResult],
        cancelled: set[str],
    ) -> bool:
        if nid in cancelled:
            return False
        node = node_map[nid]
        known_ids = set(node_map.keys())
        for d in node.depends_on:
            if d not in known_ids:
                continue
            if d not in node_results:
                return False
            if not node_results[d].success:
                return False
        return True

    def _save_checkpoint(self, ckpt_key: str, node_id: str, result: AgentResult) -> None:
        self._checkpoints.setdefault(ckpt_key, {})
        self._checkpoints[ckpt_key][node_id] = result

    async def execute_graph(
        self,
        nodes: list[TaskNode],
        on_progress: Callable[[str, AgentStatus], None] | None = None,
        approval_callback: Callable[[str, AgentSpawnConfig], Awaitable[bool]] | None = None,
    ) -> TaskGraphResult:
        """Execute a DAG of tasks with conditional routing and approval gates."""
        return await self._execute_graph_inner(
            nodes=nodes,
            on_progress=on_progress,
            approval_callback=approval_callback,
            ckpt_key=str(uuid.uuid4())[:16],
            initial_node_results={},
            initial_execution_order=[],
            initial_errors=None,
            initial_cancelled=None,
            resume_node_id=None,
            bypass_approval_for_resume=False,
        )

    async def resume_graph(
        self,
        graph_result: TaskGraphResult,
        nodes: list[TaskNode],
        approved: bool = True,
    ) -> TaskGraphResult:
        """Resume a graph that was waiting for approval."""
        if not graph_result.waiting_approval:
            return TaskGraphResult(
                success=graph_result.success,
                node_results=dict(graph_result.node_results),
                execution_order=list(graph_result.execution_order),
                errors=list(graph_result.errors),
                waiting_approval="",
            )

        cancelled_initial = getattr(graph_result, "_graph_cancelled", set())
        cancelled: set[str] = set(cancelled_initial)

        merged_errors = list(graph_result.errors)

        graph_result_clone = TaskGraphResult(
            success=graph_result.success,
            node_results=dict(graph_result.node_results),
            execution_order=list(graph_result.execution_order),
            errors=merged_errors,
            waiting_approval="",
        )
        setattr(graph_result_clone, "_graph_cancelled", cancelled)

        if not approved:
            graph_result_clone.success = False
            graph_result_clone.errors.append("resume_graph: approval denied")
            return graph_result_clone

        wid = graph_result.waiting_approval

        return await self._execute_graph_inner(
            nodes=nodes,
            on_progress=None,
            approval_callback=None,
            ckpt_key=str(uuid.uuid4())[:16],
            initial_node_results=graph_result_clone.node_results,
            initial_execution_order=graph_result_clone.execution_order,
            initial_errors=graph_result_clone.errors,
            initial_cancelled=cancelled,
            resume_node_id=wid,
            bypass_approval_for_resume=True,
        )

    async def _execute_graph_inner(
        self,
        nodes: list[TaskNode],
        on_progress: Callable[[str, AgentStatus], None] | None,
        approval_callback: Callable[[str, AgentSpawnConfig], Awaitable[bool]] | None,
        ckpt_key: str,
        initial_node_results: dict[str, AgentResult],
        initial_execution_order: list[str],
        initial_errors: list[str] | None,
        initial_cancelled: set[str] | None,
        resume_node_id: str | None,
        bypass_approval_for_resume: bool,
    ) -> TaskGraphResult:
        node_map = {n.id: n for n in nodes}
        if len(node_map) != len(nodes):
            return TaskGraphResult(success=False, errors=["Duplicate task node ids"])

        node_results: dict[str, AgentResult] = dict(initial_node_results)
        execution_order: list[str] = list(initial_execution_order)
        errors: list[str] = list(initial_errors or [])
        cancelled: set[str] = set(initial_cancelled or ())

        layers = self._topological_sort(nodes)
        if not layers and nodes:
            return TaskGraphResult(
                success=False,
                node_results=node_results,
                execution_order=execution_order,
                errors=errors + ["Cycle detected in task graph or invalid dependencies"],
                waiting_approval="",
            )

        def waiting_result(wid: str) -> TaskGraphResult:
            return TaskGraphResult(
                success=False,
                node_results=dict(node_results),
                execution_order=list(execution_order),
                errors=list(errors),
                waiting_approval=wid,
            )

        async def _run_node_graph(node: TaskNode) -> tuple[str, AgentResult]:
            if on_progress:
                on_progress(node.id, AgentStatus.RUNNING)
            last_res = AgentResult(success=False, error="not executed")
            max_attempts = node.max_retries + 1
            node.retry_count = 0
            for attempt_idx in range(max_attempts):
                last_res = await self.spawn_agent(node.config, None)
                if last_res.success:
                    break
                if attempt_idx + 1 < max_attempts:
                    node.retry_count += 1
                    logger.info(
                        f"Retrying graph node {node.id} "
                        f"({attempt_idx + 2}/{max_attempts})"
                    )

            if on_progress:
                on_progress(
                    node.id,
                    AgentStatus.COMPLETED if last_res.success else AgentStatus.FAILED,
                )
            return node.id, last_res

        for layer in layers:
            runnable: list[TaskNode] = []
            for nid in sorted(layer):
                if nid in cancelled or nid in node_results:
                    continue
                if not self._node_deps_satisfied_for_graph(nid, node_map, node_results, cancelled):
                    continue
                runnable.append(node_map[nid])

            if not runnable:
                continue

            for n in runnable:
                needs_gate = bool(n.requires_approval)
                if needs_gate:
                    bypass = bypass_approval_for_resume and resume_node_id == n.id
                    if not bypass:
                        if approval_callback is None:
                            out_w = waiting_result(n.id)
                            setattr(out_w, "_graph_cancelled", set(cancelled))
                            if on_progress:
                                on_progress(n.id, AgentStatus.WAITING_APPROVAL)
                            return out_w
                        try:
                            approved_ok = bool(await approval_callback(n.id, n.config))
                        except Exception as e:
                            approved_ok = False
                            errors.append(f"approval_callback error for {n.id}: {e}")
                        if not approved_ok:
                            out_w = waiting_result(n.id)
                            setattr(out_w, "_graph_cancelled", set(cancelled))
                            out_w.errors = list(errors)
                            if on_progress:
                                on_progress(n.id, AgentStatus.WAITING_APPROVAL)
                            return out_w

            results = await asyncio.gather(*[_run_node_graph(n) for n in runnable])

            for nid, res in results:
                node_results[nid] = res
                if nid not in execution_order:
                    execution_order.append(nid)

                try:
                    self._save_checkpoint(ckpt_key, nid, res)
                except Exception as e:
                    logger.warning(f"checkpoint write failed for {ckpt_key}/{nid}: {e}")

                parent = node_map[nid]
                if res.success:
                    self._apply_router_cancellations(node_map, parent, res, cancelled, errors)
                else:
                    self._propagate_dependency_failures(node_map, nid, cancelled)

        executed_non_cancelled = {
            nid for nid in node_map if nid not in cancelled and nid in node_results
        }
        all_executed_expected = True
        for nid in sorted(node_map.keys()):
            if nid in cancelled:
                continue
            if nid not in node_results:
                errors.append(f"Node {nid!r} was not executed")
                all_executed_expected = False

        all_ok = all_executed_expected and all(
            node_results[nid].success for nid in executed_non_cancelled
        )

        out_final = TaskGraphResult(
            success=all_ok,
            node_results=dict(node_results),
            execution_order=list(execution_order),
            errors=list(errors),
            waiting_approval="",
        )
        setattr(out_final, "_graph_cancelled", set(cancelled))
        return out_final

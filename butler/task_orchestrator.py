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
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

from butler.report import AgentReport, cache_report

logger = logging.getLogger(__name__)


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
    router: Callable[[AgentResult], str | None] | None = None
    requires_approval: bool = False
    max_retries: int = 1


@dataclass
class TaskGraphResult:
    nodes: dict[str, AgentResult] = field(default_factory=dict)
    execution_order: list[str] = field(default_factory=list)
    success: bool = True
    error: str = ""


class TaskOrchestrator:
    """Execute multi-agent workflows using Butler's AgentLoop."""

    def __init__(self) -> None:
        self._tasks: dict[str, AgentTask] = {}

    def _create_agent_loop(self, config: AgentSpawnConfig):
        """Create a Butler AgentLoop for the given config."""
        from butler.orchestrator import ButlerOrchestrator
        from butler.tools.registry import get_tool_definitions, dispatch_tool
        from butler.core.agent_loop import LoopConfig

        orch = ButlerOrchestrator(user_id="owner", channel="orchestrator")

        if config.model_config:
            from butler.config import ModelConfig
            mc = ModelConfig(**config.model_config)
            orch._settings.set_runtime_model_override(config.role, mc)

        tools = get_tool_definitions()
        delegated_tools = [t for t in tools if t["function"]["name"] != "delegate_task"]

        if config.tools:
            tool_names = set(config.tools)
            delegated_tools = [t for t in delegated_tools
                               if t["function"]["name"] in tool_names]

        agent = orch.create_project_agent_loop(
            role=config.role,
            tools=delegated_tools,
            tool_dispatcher=dispatch_tool,
        )

        agent.config.max_iterations = config.max_iterations
        return agent

    async def spawn_agent(
        self,
        config: AgentSpawnConfig,
        on_progress: Callable[[str, str, str], None] | None = None,
    ) -> AgentResult:
        """Spawn a Butler AgentLoop and run the task."""
        task_id = uuid.uuid4().hex[:8]
        task = AgentTask(id=task_id, config=config)
        self._tasks[task_id] = task
        task.status = AgentStatus.RUNNING
        task.started_at = time.time()

        logger.info("Spawning %s agent [%s]: %s", config.role, task_id, config.task[:80])

        try:
            agent = self._create_agent_loop(config)

            user_message = config.task
            if config.context:
                user_message = f"## 上下文\n{config.context}\n\n## 任务\n{config.task}"

            loop_result = await asyncio.to_thread(agent.run, user_message)

            report = AgentReport(
                headline=f"{config.role} 代理完成任务",
                summary=loop_result.final_response or "",
                success=loop_result.status.value == "completed",
                iterations=loop_result.iterations,
                tool_calls=loop_result.tool_calls_made,
                tokens_used=loop_result.total_tokens,
                elapsed_seconds=loop_result.elapsed_seconds,
            )
            cache_report(report)

            result = AgentResult(
                success=True,
                response=loop_result.final_response or "",
                report=report,
                tokens_used=loop_result.total_tokens,
                iterations=loop_result.iterations,
                tool_calls=loop_result.tool_calls_made,
                elapsed_seconds=loop_result.elapsed_seconds,
            )
        except Exception as exc:
            logger.error("Agent [%s] failed: %s", task_id, exc)
            result = AgentResult(success=False, error=str(exc))

        task.completed_at = time.time()
        task.status = AgentStatus.COMPLETED if result.success else AgentStatus.FAILED
        task.result = result

        elapsed = task.completed_at - task.started_at
        logger.info("Agent [%s] %s in %.1fs", task_id, task.status.value, elapsed)

        return result

    async def spawn_parallel(self, configs: list[AgentSpawnConfig]) -> list[AgentResult]:
        """Spawn multiple agents in true parallel via asyncio.to_thread."""
        tasks = [self.spawn_agent(cfg) for cfg in configs]
        return list(await asyncio.gather(*tasks, return_exceptions=False))

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
    ) -> TaskGraphResult:
        """Execute a DAG of tasks with dependency resolution."""
        graph_result = TaskGraphResult()
        node_map = {n.id: n for n in nodes}
        completed: dict[str, AgentResult] = {}

        order = _topological_sort(nodes)

        layers = _group_into_layers(order, node_map)

        for layer in layers:
            layer_tasks = []
            for node_id in layer:
                node = node_map[node_id]

                if node.depends_on:
                    dep_contexts = []
                    for dep_id in node.depends_on:
                        dep_result = completed.get(dep_id)
                        if dep_result and dep_result.response:
                            dep_contexts.append(f"[{dep_id} 结果]: {dep_result.response[:1500]}")
                    if dep_contexts:
                        node.config.context = (
                            (node.config.context or "") + "\n\n" + "\n".join(dep_contexts)
                        )

                if node.requires_approval and on_approval:
                    if not on_approval(node):
                        completed[node_id] = AgentResult(
                            success=False, error="Approval denied"
                        )
                        continue

                layer_tasks.append((node_id, node))

            if not layer_tasks:
                continue

            if len(layer_tasks) == 1:
                nid, node = layer_tasks[0]
                result = await self._run_with_retry(node)
                completed[nid] = result
                graph_result.execution_order.append(nid)
            else:
                parallel_results = await asyncio.gather(
                    *[self._run_with_retry(node) for _, node in layer_tasks]
                )
                for (nid, _), result in zip(layer_tasks, parallel_results):
                    completed[nid] = result
                    graph_result.execution_order.append(nid)

            for nid in [lid for lid, _ in layer_tasks]:
                node = node_map[nid]
                result = completed[nid]
                if node.router and result.success:
                    next_id = node.router(result)
                    if next_id and next_id in node_map and next_id not in completed:
                        extra_result = await self._run_with_retry(node_map[next_id])
                        completed[next_id] = extra_result
                        graph_result.execution_order.append(next_id)

        graph_result.nodes = completed
        graph_result.success = all(r.success for r in completed.values())
        return graph_result

    async def _run_with_retry(self, node: TaskNode) -> AgentResult:
        last_result = AgentResult(success=False, error="No attempts")
        for attempt in range(node.max_retries):
            last_result = await self.spawn_agent(node.config)
            if last_result.success:
                return last_result
            logger.warning(
                "Node %s attempt %d/%d failed",
                node.id, attempt + 1, node.max_retries,
            )
        return last_result


def _topological_sort(nodes: list[TaskNode]) -> list[str]:
    """Kahn's algorithm for topological ordering."""
    graph: dict[str, list[str]] = {n.id: [] for n in nodes}
    in_degree: dict[str, int] = {n.id: 0 for n in nodes}

    for n in nodes:
        for dep in n.depends_on:
            if dep in graph:
                graph[dep].append(n.id)
                in_degree[n.id] += 1

    queue = [nid for nid, deg in in_degree.items() if deg == 0]
    result = []

    while queue:
        nid = queue.pop(0)
        result.append(nid)
        for neighbor in graph.get(nid, []):
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if len(result) != len(nodes):
        raise ValueError("Task graph contains a cycle")

    return result


def _group_into_layers(
    order: list[str],
    node_map: dict[str, TaskNode],
) -> list[list[str]]:
    """Group topologically sorted nodes into parallel layers."""
    depth: dict[str, int] = {}
    for nid in order:
        node = node_map[nid]
        if not node.depends_on:
            depth[nid] = 0
        else:
            depth[nid] = max(depth.get(d, 0) for d in node.depends_on) + 1

    max_depth = max(depth.values()) if depth else 0
    layers: list[list[str]] = [[] for _ in range(max_depth + 1)]
    for nid in order:
        layers[depth[nid]].append(nid)

    return [layer for layer in layers if layer]

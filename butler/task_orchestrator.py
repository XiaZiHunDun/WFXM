"""DAG task orchestration engine for Butler v3.

Manages multi-agent workflows: spawn single/parallel/sequential/background
tasks, execute DAG graphs with conditional routing and approval gates.

Unlike v1 which used a custom AgentRunner, v3 spawns Hermes AIAgent
instances for each task, getting the full Hermes tool ecosystem.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable

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
    """Configuration for spawning a project-level agent."""
    role: str
    task: str
    project_name: str = ""
    max_iterations: int = 90
    context: str = ""
    output_format: str = ""


@dataclass
class AgentResult:
    """Structured output from a completed agent."""
    success: bool = True
    response: str = ""
    summary: str = ""
    artifacts: list[str] = field(default_factory=list)
    turns_used: int = 0
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
    router: Callable[[AgentResult], str] | None = None
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
    waiting_approval: str = ""


class TaskOrchestrator:
    """Manages agent lifecycle using Hermes AIAgent as the execution engine."""

    def __init__(self, orchestrator: Any = None):
        self._tasks: dict[str, AgentTask] = {}
        self._checkpoints: dict[str, dict[str, AgentResult]] = {}
        self._orchestrator = orchestrator

    def _spawn_hermes_agent(self, config: AgentSpawnConfig) -> Any:
        """Create a Hermes AIAgent for the given config."""
        from butler.main import _ensure_hermes_env, _create_project_agent

        _ensure_hermes_env()
        if self._orchestrator is None:
            from butler.orchestrator import ButlerOrchestrator
            self._orchestrator = ButlerOrchestrator()

        if config.project_name:
            self._orchestrator.project_manager.switch_project(config.project_name)

        from butler.agent_profiles import get_profile, get_model_aware_prompt_extra
        profile = get_profile(config.role)

        agent = _create_project_agent(
            self._orchestrator,
            config.role,
            session_id=f"task-{uuid.uuid4().hex[:8]}",
            quiet_mode=True,
        )

        if profile:
            provider = getattr(agent, "provider", "") or ""
            extra = get_model_aware_prompt_extra(provider)
            if extra and hasattr(agent, "ephemeral_system_prompt"):
                current = getattr(agent, "ephemeral_system_prompt", "") or ""
                agent.ephemeral_system_prompt = current + extra

        return agent

    async def spawn_agent(
        self,
        config: AgentSpawnConfig,
        on_progress: Callable[[int, str, str], None] | None = None,
    ) -> AgentResult:
        """Spawn a Hermes AIAgent and run the task."""
        task_id = uuid.uuid4().hex[:8]
        task = AgentTask(id=task_id, config=config)
        self._tasks[task_id] = task
        task.status = AgentStatus.RUNNING
        task.started_at = time.time()

        logger.info("Spawning %s agent [%s]: %s", config.role, task_id, config.task[:80])

        try:
            agent = self._spawn_hermes_agent(config)

            user_message = config.task
            if config.context:
                user_message = f"## 上下文\n{config.context}\n\n## 任务\n{config.task}"

            raw_result = agent.run_conversation(user_message=user_message)

            response = ""
            if isinstance(raw_result, dict):
                response = raw_result.get("response", "")
            else:
                response = str(raw_result)

            result = AgentResult(
                success=True,
                response=response,
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
        """Spawn multiple agents in parallel."""
        tasks = [self.spawn_agent(cfg) for cfg in configs]
        return list(await asyncio.gather(*tasks, return_exceptions=False))

    async def spawn_sequential(
        self,
        configs: list[AgentSpawnConfig],
        pass_context: bool = True,
    ) -> list[AgentResult]:
        """Spawn agents sequentially with optional context passing."""
        results: list[AgentResult] = []
        accumulated_context = ""
        for cfg in configs:
            if pass_context and accumulated_context:
                cfg.context = (cfg.context + "\n\n前序 Agent 输出:\n" + accumulated_context).strip()
            result = await self.spawn_agent(cfg)
            results.append(result)
            if result.success:
                accumulated_context = result.response[:2000]
            else:
                break
        return results

    async def spawn_background(
        self,
        config: AgentSpawnConfig,
        on_complete: Callable[[AgentResult], Any] | None = None,
    ) -> str:
        """Spawn an agent in background, return task ID."""
        task_id = uuid.uuid4().hex[:8]

        async def _run():
            result = await self.spawn_agent(config)
            if on_complete:
                if asyncio.iscoroutinefunction(on_complete):
                    await on_complete(result)
                else:
                    on_complete(result)

        asyncio.create_task(_run())
        return task_id

    def get_task(self, task_id: str) -> AgentTask | None:
        return self._tasks.get(task_id)

    def list_tasks(self, status: AgentStatus | None = None) -> list[AgentTask]:
        tasks = list(self._tasks.values())
        if status:
            tasks = [t for t in tasks if t.status == status]
        return sorted(tasks, key=lambda t: t.started_at, reverse=True)

    def _topological_sort(self, nodes: list[TaskNode]) -> list[list[str]]:
        """Returns layers of node IDs for parallel execution."""
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

        if sum(len(layer) for layer in layers) != len(node_ids):
            return []
        return layers

    async def execute_graph(
        self,
        nodes: list[TaskNode],
        on_progress: Callable[[str, AgentStatus], None] | None = None,
        approval_callback: Callable[[str, AgentSpawnConfig], Awaitable[bool]] | None = None,
    ) -> TaskGraphResult:
        """Execute a DAG of tasks with conditional routing and approval gates."""
        node_map = {n.id: n for n in nodes}
        node_results: dict[str, AgentResult] = {}
        execution_order: list[str] = []
        errors: list[str] = []
        cancelled: set[str] = set()

        layers = self._topological_sort(nodes)
        if not layers and nodes:
            return TaskGraphResult(
                success=False, errors=["Cycle detected in task graph"]
            )

        for layer in layers:
            runnable = [
                node_map[nid] for nid in sorted(layer)
                if nid not in cancelled and nid not in node_results
            ]
            if not runnable:
                continue

            for n in runnable:
                if n.requires_approval and approval_callback:
                    try:
                        approved = bool(await approval_callback(n.id, n.config))
                    except Exception as e:
                        approved = False
                        errors.append(f"approval error for {n.id}: {e}")
                    if not approved:
                        return TaskGraphResult(
                            success=False,
                            node_results=node_results,
                            execution_order=execution_order,
                            errors=errors,
                            waiting_approval=n.id,
                        )

            async def _run_node(node: TaskNode) -> tuple[str, AgentResult]:
                if on_progress:
                    on_progress(node.id, AgentStatus.RUNNING)
                last_res = AgentResult(success=False, error="not executed")
                for attempt in range(node.max_retries + 1):
                    last_res = await self.spawn_agent(node.config)
                    if last_res.success:
                        break
                if on_progress:
                    status = AgentStatus.COMPLETED if last_res.success else AgentStatus.FAILED
                    on_progress(node.id, status)
                return node.id, last_res

            results = await asyncio.gather(*[_run_node(n) for n in runnable])

            for nid, res in results:
                node_results[nid] = res
                execution_order.append(nid)
                if not res.success:
                    for dep in node_map.values():
                        if nid in dep.depends_on:
                            cancelled.add(dep.id)

                if res.success and node_map[nid].router:
                    try:
                        next_id = node_map[nid].router(res)
                        if next_id:
                            direct_deps = [
                                d.id for d in node_map.values()
                                if nid in d.depends_on and d.id != next_id
                            ]
                            cancelled.update(direct_deps)
                    except Exception as e:
                        errors.append(f"router error for {nid}: {e}")

        all_ok = all(
            node_results[nid].success
            for nid in node_map
            if nid not in cancelled and nid in node_results
        )

        return TaskGraphResult(
            success=all_ok,
            node_results=node_results,
            execution_order=execution_order,
            errors=errors,
        )

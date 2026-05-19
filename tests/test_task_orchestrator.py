"""L3 integration tests for butler.task_orchestrator."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from butler.core.agent_loop import LoopResult, LoopStatus
from butler.task_orchestrator import (
    AgentResult,
    AgentSpawnConfig,
    TaskNode,
    TaskOrchestrator,
    _group_into_layers,
    _topological_sort,
)


def _spawn_config(role: str = "dev", task: str = "do work") -> AgentSpawnConfig:
    return AgentSpawnConfig(role=role, task=task)


def _completed_loop_result(
    response: str = "done",
    tokens: int = 100,
    iterations: int = 2,
    tool_calls: int = 1,
    elapsed: float = 1.5,
) -> LoopResult:
    return LoopResult(
        status=LoopStatus.COMPLETED,
        final_response=response,
        iterations=iterations,
        total_tokens=tokens,
        tool_calls_made=tool_calls,
        elapsed_seconds=elapsed,
    )


def _mock_agent_loop(result: LoopResult | None = None, run_side_effect=None):
    loop = MagicMock()
    if run_side_effect is not None:
        loop.run.side_effect = run_side_effect
    else:
        loop.run.return_value = result or _completed_loop_result()
    loop.config = MagicMock(max_iterations=30)
    return loop


@pytest.mark.integration
class TestTopology:
    def test_topological_sort_linear_chain(self):
        nodes = [
            TaskNode(id="a", config=_spawn_config(), depends_on=[]),
            TaskNode(id="b", config=_spawn_config(), depends_on=["a"]),
            TaskNode(id="c", config=_spawn_config(), depends_on=["b"]),
        ]
        order = _topological_sort(nodes)
        assert order.index("a") < order.index("b") < order.index("c")

    def test_topological_sort_parallel_nodes(self):
        nodes = [
            TaskNode(id="a", config=_spawn_config(), depends_on=[]),
            TaskNode(id="b", config=_spawn_config(), depends_on=[]),
            TaskNode(id="c", config=_spawn_config(), depends_on=["a", "b"]),
        ]
        order = _topological_sort(nodes)
        assert order.index("a") < order.index("c")
        assert order.index("b") < order.index("c")

    def test_topological_sort_cycle_raises(self):
        nodes = [
            TaskNode(id="a", config=_spawn_config(), depends_on=["b"]),
            TaskNode(id="b", config=_spawn_config(), depends_on=["a"]),
        ]
        with pytest.raises(ValueError, match="cycle"):
            _topological_sort(nodes)

    def test_group_into_layers_correct_grouping(self):
        nodes = [
            TaskNode(id="a", config=_spawn_config(), depends_on=[]),
            TaskNode(id="b", config=_spawn_config(), depends_on=[]),
            TaskNode(id="c", config=_spawn_config(), depends_on=["a", "b"]),
        ]
        order = _topological_sort(nodes)
        node_map = {n.id: n for n in nodes}
        layers = _group_into_layers(order, node_map)
        assert set(layers[0]) == {"a", "b"}
        assert layers[1] == ["c"]


@pytest.mark.integration
class TestSpawnAgent:
    @pytest.mark.asyncio
    async def test_spawn_agent_creates_loop_and_calls_run(self):
        orch = TaskOrchestrator()
        mock_loop = _mock_agent_loop()

        with patch.object(orch, "_create_agent_loop", return_value=mock_loop):
            result = await orch.spawn_agent(_spawn_config(task="run tests"))

        mock_loop.run.assert_called_once()
        assert "run tests" in mock_loop.run.call_args[0][0]

    @pytest.mark.asyncio
    async def test_agent_result_success_fields(self):
        orch = TaskOrchestrator()
        mock_loop = _mock_agent_loop(
            _completed_loop_result("hello", tokens=42, iterations=3, tool_calls=2, elapsed=2.0)
        )

        with patch.object(orch, "_create_agent_loop", return_value=mock_loop):
            result = await orch.spawn_agent(_spawn_config())

        assert result.success is True
        assert result.response == "hello"
        assert result.tokens_used == 42
        assert result.iterations == 3
        assert result.tool_calls == 2
        assert result.elapsed_seconds == 2.0
        assert result.report is not None

    @pytest.mark.asyncio
    async def test_failed_agent_success_false(self):
        orch = TaskOrchestrator()
        mock_loop = _mock_agent_loop()
        mock_loop.run.side_effect = RuntimeError("LLM down")

        with patch.object(orch, "_create_agent_loop", return_value=mock_loop):
            result = await orch.spawn_agent(_spawn_config())

        assert result.success is False
        assert "LLM down" in result.error


@pytest.mark.integration
class TestSpawnParallel:
    @pytest.mark.asyncio
    async def test_two_parallel_agents_both_complete(self):
        orch = TaskOrchestrator()
        results = [
            AgentResult(success=True, response="a"),
            AgentResult(success=True, response="b"),
        ]

        with patch.object(orch, "spawn_agent", new_callable=AsyncMock) as mock_spawn:
            mock_spawn.side_effect = results
            out = await orch.spawn_parallel([_spawn_config(), _spawn_config(role="review")])

        assert len(out) == 2
        assert all(r.success for r in out)

    @pytest.mark.asyncio
    async def test_one_fails_results_contain_failure(self):
        orch = TaskOrchestrator()

        with patch.object(
            orch,
            "spawn_agent",
            new_callable=AsyncMock,
            side_effect=[
                AgentResult(success=True, response="ok"),
                AgentResult(success=False, error="fail"),
            ],
        ):
            out = await orch.spawn_parallel([_spawn_config(), _spawn_config(role="review")])

        assert out[0].success is True
        assert out[1].success is False


@pytest.mark.integration
class TestSpawnSequential:
    @pytest.mark.asyncio
    async def test_three_sequential_steps(self):
        orch = TaskOrchestrator()
        call_count = 0

        async def _fake_spawn(cfg: AgentSpawnConfig) -> AgentResult:
            nonlocal call_count
            call_count += 1
            return AgentResult(success=True, response=f"step-{call_count}")

        with patch.object(orch, "spawn_agent", side_effect=_fake_spawn):
            results = await orch.spawn_sequential(
                [_spawn_config(role="dev"), _spawn_config(role="content"), _spawn_config(role="review")]
            )

        assert len(results) == 3
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_step_failure_stops_chain(self):
        orch = TaskOrchestrator()

        with patch.object(
            orch,
            "spawn_agent",
            new_callable=AsyncMock,
            side_effect=[
                AgentResult(success=True, response="ok"),
                AgentResult(success=False, error="broken"),
                AgentResult(success=True, response="never"),
            ],
        ):
            results = await orch.spawn_sequential(
                [_spawn_config(), _spawn_config(role="content"), _spawn_config(role="review")]
            )

        assert len(results) == 2
        assert results[1].success is False


@pytest.mark.integration
class TestExecuteGraph:
    @pytest.mark.asyncio
    async def test_simple_two_node_dag(self):
        orch = TaskOrchestrator()
        nodes = [
            TaskNode(id="n1", config=_spawn_config(task="first")),
            TaskNode(id="n2", config=_spawn_config(task="second"), depends_on=["n1"]),
        ]

        with patch.object(
            orch,
            "spawn_agent",
            new_callable=AsyncMock,
            return_value=AgentResult(success=True, response="ok"),
        ) as mock_spawn:
            graph = await orch.execute_graph(nodes)

        assert graph.success is True
        assert "n1" in graph.nodes
        assert "n2" in graph.nodes
        assert mock_spawn.call_count >= 2

    @pytest.mark.asyncio
    async def test_with_dependencies_passes_context(self):
        orch = TaskOrchestrator()
        captured_contexts: list[str] = []

        async def _spawn(cfg: AgentSpawnConfig) -> AgentResult:
            captured_contexts.append(cfg.context)
            if cfg.task == "second":
                assert "n1" in cfg.context or "结果" in cfg.context
            return AgentResult(success=True, response=f"resp-{cfg.task}")

        nodes = [
            TaskNode(id="n1", config=_spawn_config(task="first")),
            TaskNode(id="n2", config=_spawn_config(task="second"), depends_on=["n1"]),
        ]

        with patch.object(orch, "spawn_agent", side_effect=_spawn):
            graph = await orch.execute_graph(nodes)

        assert graph.success is True
        assert len(captured_contexts) >= 1

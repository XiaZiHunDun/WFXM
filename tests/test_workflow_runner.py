"""Tests for butler.workflows.runner — DAG execution, error, and summary scenarios."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from butler.task_orchestrator import AgentResult, TaskGraphResult
from butler.workflows.runner import WorkflowRunner
from butler.workflows.schema import parse_workflow_data


def _simple_workflow(steps=None, name="test-wf"):
    if steps is None:
        steps = [
            {"id": "a", "role": "dev", "task": "step a"},
            {"id": "b", "role": "review", "task": "step b", "depends_on": ["a"]},
        ]
    return parse_workflow_data({"name": name, "steps": steps})


class TestBuildNodes:
    def test_not_runnable_raises(self):
        wf = parse_workflow_data({"name": "empty"})
        runner = WorkflowRunner(orchestrator=MagicMock())
        with pytest.raises(ValueError, match="没有可执行步骤"):
            runner.build_nodes(wf)

    def test_user_hint_appended(self):
        wf = _simple_workflow()
        runner = WorkflowRunner(orchestrator=MagicMock())
        nodes = runner.build_nodes(wf, user_hint="注意安全")
        assert "注意安全" in nodes[0].config.task
        assert "注意安全" in nodes[1].config.task

    def test_depends_on_preserved(self):
        wf = _simple_workflow()
        runner = WorkflowRunner(orchestrator=MagicMock())
        nodes = runner.build_nodes(wf)
        assert nodes[0].depends_on == []
        assert nodes[1].depends_on == ["a"]


class TestFormatGraphSummary:
    def test_success_summary(self):
        wf = _simple_workflow()
        graph = TaskGraphResult(
            success=True,
            nodes={
                "a": AgentResult(success=True, response="done a"),
                "b": AgentResult(success=True, response="done b"),
            },
            execution_order=["a", "b"],
        )
        runner = WorkflowRunner(orchestrator=MagicMock())
        text = runner.format_graph_summary(wf, graph)
        assert "已完成" in text
        assert "✓ a" in text
        assert "✓ b" in text

    def test_failure_summary(self):
        wf = _simple_workflow()
        graph = TaskGraphResult(
            success=False,
            nodes={
                "a": AgentResult(success=True, response="done a"),
                "b": AgentResult(success=False, response="", error="timeout"),
            },
            execution_order=["a", "b"],
        )
        runner = WorkflowRunner(orchestrator=MagicMock())
        text = runner.format_graph_summary(wf, graph)
        assert "未完全成功" in text
        assert "✗ b" in text

    def test_long_response_truncated(self):
        wf = _simple_workflow(
            steps=[{"id": "x", "role": "dev", "task": "step x"}]
        )
        graph = TaskGraphResult(
            success=True,
            nodes={"x": AgentResult(success=True, response="R" * 500)},
            execution_order=["x"],
        )
        runner = WorkflowRunner(orchestrator=MagicMock())
        text = runner.format_graph_summary(wf, graph)
        assert "..." in text

    def test_graph_error_included(self):
        wf = _simple_workflow()
        graph = TaskGraphResult(
            success=False,
            nodes={},
            execution_order=[],
            error="dag cycle detected",
        )
        runner = WorkflowRunner(orchestrator=MagicMock())
        text = runner.format_graph_summary(wf, graph)
        assert "dag cycle detected" in text


class TestCacheWorkflowReport:
    def test_step_outcomes_recorded(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
        from butler.config import reload_butler_settings

        reload_butler_settings()
        from butler.report import clear_report_cache

        clear_report_cache()

        wf = _simple_workflow()
        graph = TaskGraphResult(
            success=True,
            nodes={
                "a": AgentResult(success=True, response="ok a"),
                "b": AgentResult(success=True, response="ok b"),
            },
            execution_order=["a", "b"],
        )
        WorkflowRunner._cache_workflow_report(wf, graph, session_key="test-sess")

        from butler.report import get_last_report

        report = get_last_report("test-sess")
        assert report is not None
        assert report.step_outcomes["a"] == "ok"
        assert report.step_outcomes["b"] == "ok"

    def test_failed_step_recorded(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
        from butler.config import reload_butler_settings

        reload_butler_settings()
        from butler.report import clear_report_cache

        clear_report_cache()

        wf = _simple_workflow()
        graph = TaskGraphResult(
            success=False,
            nodes={
                "a": AgentResult(success=True, response="ok"),
                "b": AgentResult(success=False, response="", error="fail"),
            },
            execution_order=["a", "b"],
        )
        WorkflowRunner._cache_workflow_report(wf, graph, session_key="fail-sess")

        from butler.report import get_last_report

        report = get_last_report("fail-sess")
        assert report is not None
        assert report.step_outcomes["b"] == "fail"
        assert "b" in report.failed_steps

    def test_approval_pending_step(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
        from butler.config import reload_butler_settings

        reload_butler_settings()
        from butler.report import clear_report_cache

        clear_report_cache()

        wf = _simple_workflow()
        graph = TaskGraphResult(
            success=False,
            nodes={
                "a": AgentResult(success=True, response="ok"),
                "b": AgentResult(
                    success=False,
                    response="",
                    error="workflow_step_approval_pending",
                ),
            },
            execution_order=["a", "b"],
        )
        WorkflowRunner._cache_workflow_report(wf, graph, session_key="pend-sess")

        from butler.report import get_last_report

        report = get_last_report("pend-sess")
        assert report is not None
        assert report.step_outcomes["b"] == "approval_pending"
        assert "待确认" in report.headline


class TestRunAsync:
    @pytest.mark.asyncio
    async def test_partial_failure(self):
        wf = _simple_workflow()
        graph = TaskGraphResult(
            success=False,
            nodes={
                "a": AgentResult(success=True, response="ok"),
                "b": AgentResult(success=False, response="", error="crash"),
            },
            execution_order=["a", "b"],
        )
        runner = WorkflowRunner(orchestrator=MagicMock())
        with patch.object(
            runner._tasks, "execute_graph", new_callable=AsyncMock
        ) as mock_graph:
            mock_graph.return_value = graph
            result = await runner.run_async(wf, session_key="s1")
        assert not result.success

    @pytest.mark.asyncio
    async def test_single_step_workflow(self):
        wf = _simple_workflow(
            steps=[{"id": "only", "role": "dev", "task": "just this"}]
        )
        graph = TaskGraphResult(
            success=True,
            nodes={"only": AgentResult(success=True, response="done")},
            execution_order=["only"],
        )
        runner = WorkflowRunner(orchestrator=MagicMock())
        with patch.object(
            runner._tasks, "execute_graph", new_callable=AsyncMock
        ) as mock_graph:
            mock_graph.return_value = graph
            result = await runner.run_async(wf, session_key="s2")
        assert result.success


class TestRunSync:
    def test_run_delegates_to_async(self):
        wf = _simple_workflow()
        graph = TaskGraphResult(
            success=True,
            nodes={
                "a": AgentResult(success=True, response="ok"),
                "b": AgentResult(success=True, response="ok"),
            },
            execution_order=["a", "b"],
        )
        runner = WorkflowRunner(orchestrator=MagicMock())
        with patch.object(
            runner._tasks, "execute_graph", new_callable=AsyncMock
        ) as mock_graph:
            mock_graph.return_value = graph
            result = runner.run(wf, session_key="s3")
        assert result.success

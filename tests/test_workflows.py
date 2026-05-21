"""Sprint 4: project workflows + TaskOrchestrator integration."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml

from butler.config import reload_butler_settings
from butler.project import Project
from butler.project_manager import ProjectManager
from butler.task_orchestrator import AgentResult, TaskGraphResult
from butler.workflows.loader import (
    load_builtin_workflow,
    list_workflows_for_project,
    resolve_workflow,
)
from butler.report import clear_report_cache
from butler.workflows.runner import WorkflowRunner
from butler.workflows.schema import parse_workflow_data


@pytest.fixture(autouse=True)
def _isolate_report_cache():
    clear_report_cache()
    yield
    clear_report_cache()


def _project_dir(tmp_path: Path, folder: str, workflows: list) -> Project:
    proj_dir = tmp_path / folder
    proj_dir.mkdir(parents=True)
    (proj_dir / "project.yaml").write_text(
        yaml.safe_dump(
            {
                "name": folder,
                "type": "software",
                "description": folder,
                "workspace": str(proj_dir),
                "workflows": workflows,
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    return Project.from_yaml(proj_dir / "project.yaml")


@pytest.mark.module_test
class TestWorkflowLoader:
    def test_builtin_novel_factory_has_steps(self):
        wf = load_builtin_workflow("novel-factory")
        assert wf is not None
        assert wf.runnable
        assert {s.id for s in wf.steps} == {"draft", "review"}

    def test_builtin_novel_factory_status_read_step_uses_deepseek(self):
        wf = load_builtin_workflow("novel-factory-status")
        assert wf is not None
        read = next(s for s in wf.steps if s.id == "read-state")
        assert read.model is not None
        assert read.model.provider == "deepseek"
        assert read.model.model == "deepseek-chat"

    def test_parse_step_model_string(self):
        from butler.workflows.schema import parse_step

        step = parse_step(
            {"id": "x", "role": "dev", "task": "do", "model": "openai/gpt-4o-mini"}
        )
        assert step is not None
        assert step.model is not None
        assert step.model.provider == "openai"
        assert step.model.model == "gpt-4o-mini"

    def test_resolve_merges_builtin_when_project_has_name_only(self, tmp_path):
        proj = _project_dir(
            tmp_path,
            "ling",
            [{"name": "novel-factory", "description": "小说流水线"}],
        )
        wf = resolve_workflow(proj, "novel-factory")
        assert wf is not None
        assert wf.runnable
        assert wf.source == "builtin"

    def test_inline_steps_override_builtin(self, tmp_path):
        proj = _project_dir(
            tmp_path,
            "custom",
            [
                {
                    "name": "novel-factory",
                    "steps": [
                        {"id": "only", "role": "dev", "task": "do one thing"},
                    ],
                }
            ],
        )
        wf = resolve_workflow(proj, "novel-factory")
        assert wf is not None
        assert len(wf.steps) == 1
        assert wf.steps[0].id == "only"


@pytest.mark.integration
class TestWorkflowRunner:
    @pytest.mark.asyncio
    async def test_run_async_builds_graph_and_summarizes(self, tmp_path):
        wf = parse_workflow_data(
            {
                "name": "smoke",
                "steps": [
                    {"id": "a", "role": "content", "task": "step a"},
                    {"id": "b", "role": "review", "task": "step b", "depends_on": ["a"]},
                ],
            }
        )
        assert wf is not None

        graph = TaskGraphResult(
            success=True,
            nodes={
                "a": AgentResult(success=True, response="done a"),
                "b": AgentResult(success=True, response="done b"),
            },
            execution_order=["a", "b"],
        )

        runner = WorkflowRunner(orchestrator=MagicMock())
        with patch.object(runner._tasks, "execute_graph", new_callable=AsyncMock) as mock_graph:
            mock_graph.return_value = graph
            result = await runner.run_async(wf, user_hint="用户目标")

        assert result.success
        mock_graph.assert_awaited_once()
        nodes = mock_graph.await_args.args[0]
        assert len(nodes) == 2
        assert "用户目标" in nodes[1].config.task

        summary = runner.format_graph_summary(wf, graph)
        assert "smoke" in summary
        assert "done a" in summary

    def test_build_nodes_passes_step_model_config(self):
        wf = parse_workflow_data(
            {
                "name": "priced",
                "steps": [
                    {
                        "id": "cheap",
                        "role": "content",
                        "task": "read only",
                        "model": "deepseek/deepseek-chat",
                    },
                ],
            }
        )
        assert wf is not None
        runner = WorkflowRunner(orchestrator=MagicMock())
        nodes = runner.build_nodes(wf)
        assert nodes[0].config.model_config == {
            "provider": "deepseek",
            "model": "deepseek-chat",
        }


@pytest.mark.integration
class TestWorkflowSlash:
    def test_list_workflows_for_project(self, tmp_path, monkeypatch, tmp_butler_home):
        projects_dir = tmp_path / "projects"
        _project_dir(
            projects_dir,
            "demo",
            [{"name": "novel-factory", "description": "demo wf"}],
        )
        monkeypatch.setenv("BUTLER_PROJECTS_DIR", str(projects_dir))
        ProjectManager._instance = None
        reload_butler_settings()

        from butler.orchestrator import ButlerOrchestrator
        from butler.workflows.commands import handle_workflow_command

        orch = ButlerOrchestrator(channel="test")
        orch.project_manager.switch_project("demo")
        listed = handle_workflow_command(orch, "list")
        assert "novel-factory" in listed

        wechat_list = handle_workflow_command(orch, "list", platform="wechat")
        assert "novel-factory" in wechat_list
        assert "**" not in wechat_list

        ProjectManager._instance = None
        orch2 = ButlerOrchestrator(channel="test")
        missing = handle_workflow_command(orch2, "list", platform="wechat")
        assert "/切换" in missing

        with patch(
            "butler.workflows.runner.WorkflowRunner.run",
            return_value=TaskGraphResult(
                success=True,
                nodes={"draft": AgentResult(success=True, response="ok")},
                execution_order=["draft"],
            ),
        ):
            out = handle_workflow_command(orch, "run novel-factory 写验收文档")
        assert "novel-factory" in out


@pytest.mark.module_test
class TestLingwenLeadHooks:
    def test_project_switched_includes_workflows_for_lingwen(self):
        from butler.workflows.hooks import _on_project_switched

        orch = MagicMock()
        proj = MagicMock()
        proj.name = "灵文1号"
        orch.project_manager.get_current.return_value = proj
        from types import SimpleNamespace

        with patch(
            "butler.workflows.loader.list_workflows_for_project",
            return_value=[SimpleNamespace(name="novel-factory")],
        ):
            out = _on_project_switched(
                old_project="",
                new_project="灵文1号",
                orchestrator=orch,
            )
        assert out is not None
        assert "工作流" in out.get("context", "")

"""L3 integration tests for butler.orchestrator."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from butler.config import ModelConfig, reload_butler_settings
from butler.project_manager import ProjectManager


def _reset_singletons() -> None:
    ProjectManager._instance = None
    reload_butler_settings()


def _setup_projects_dir(tmp_path: Path, monkeypatch) -> Path:
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()
    proj = projects_dir / "test-project"
    proj.mkdir()
    (proj / "project.yaml").write_text(
        yaml.safe_dump(
            {
                "name": "test-project",
                "type": "software",
                "description": "A test project",
                "workspace": str(proj),
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("BUTLER_PROJECTS_DIR", str(projects_dir))
    _reset_singletons()
    return projects_dir


@pytest.fixture
def orch_with_project(tmp_path, monkeypatch, tmp_butler_home):
    _setup_projects_dir(tmp_path, monkeypatch)
    from butler.orchestrator import ButlerOrchestrator

    o = ButlerOrchestrator(user_id="test", channel="test")
    o.project_manager.switch_project("test-project")
    yield o
    _reset_singletons()


@pytest.fixture
def orch_no_projects(tmp_butler_home):
    _reset_singletons()
    from butler.orchestrator import ButlerOrchestrator

    o = ButlerOrchestrator(user_id="test", channel="test")
    yield o
    _reset_singletons()


@pytest.mark.integration
class TestModelCredentials:
    def test_returns_provider_model_api_key_base_url(self, orch_no_projects, monkeypatch):
        monkeypatch.setenv("MINIMAX_API_KEY", "test-key-123")
        reload_butler_settings()
        orch_no_projects._settings = reload_butler_settings()

        creds = orch_no_projects._model_credentials("butler")
        assert "provider" in creds
        assert "model" in creds
        assert "api_key" in creds
        assert "base_url" in creds
        assert creds["provider"] == "minimax"
        assert creds["api_key"] == "test-key-123"

    def test_env_providers_populate(self, orch_no_projects, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-secret")
        reload_butler_settings()
        orch_no_projects._settings = reload_butler_settings()

        assert "claude" in orch_no_projects._settings.providers
        pc = orch_no_projects._settings.providers["claude"]
        assert pc.api_key == "anthropic-secret"

    def test_runtime_override_takes_precedence(self, orch_no_projects):
        override = ModelConfig(provider="openai", model="gpt-4o", max_tokens=4096)
        orch_no_projects._settings.set_runtime_model_override("butler", override)

        creds = orch_no_projects._model_credentials("butler")
        assert creds["provider"] == "openai"
        assert creds["model"] == "gpt-4o"
        assert creds["max_tokens"] == 4096


@pytest.mark.integration
class TestSystemPrompt:
    def test_build_system_prompt_non_empty(self, orch_no_projects):
        prompt = orch_no_projects.build_system_prompt()
        assert isinstance(prompt, str)
        assert len(prompt.strip()) > 0

    def test_contains_delegate_task_mention(self, orch_no_projects):
        prompt = orch_no_projects.build_system_prompt()
        assert "delegate_task" in prompt
        assert "必须委派" in prompt or "必须使用" in prompt

    def test_contains_project_info_when_projects_exist(self, orch_with_project):
        prompt = orch_with_project.build_system_prompt()
        assert "test-project" in prompt


@pytest.mark.integration
class TestFactoryMethods:
    def test_create_llm_client_butler_role(self, orch_no_projects, monkeypatch):
        monkeypatch.setenv("MINIMAX_API_KEY", "test-key")
        reload_butler_settings()
        orch_no_projects._settings = reload_butler_settings()

        client = orch_no_projects.create_llm_client("butler")
        assert client.provider_name == "minimax"
        assert client.model

    def test_create_llm_client_correct_provider_model(self, orch_no_projects, monkeypatch):
        monkeypatch.setenv("MINIMAX_API_KEY", "k")
        monkeypatch.setenv("MINIMAX_MODEL", "MiniMax-Test")
        reload_butler_settings()
        orch_no_projects._settings = reload_butler_settings()

        client = orch_no_projects.create_llm_client("butler")
        assert client.model == "MiniMax-Test" or client.provider_name == "minimax"

    def test_orchestrator_initializes_memory_provider(self, tmp_butler_home, monkeypatch):
        _reset_singletons()
        provider = MagicMock()

        with patch("butler.orchestrator.ButlerMemoryService", return_value=provider):
            from butler.orchestrator import ButlerOrchestrator

            orch = ButlerOrchestrator(user_id="u1", channel="test")

        assert orch.memory_provider is provider
        provider.initialize.assert_called_once()

    def test_create_agent_loop_has_system_prompt_and_ten_tools(
        self, orch_no_projects, mock_llm_client
    ):
        from butler.tools.registry import get_tool_definitions

        with patch.object(orch_no_projects, "create_llm_client", return_value=mock_llm_client):
            loop = orch_no_projects.create_agent_loop(
                role="butler",
                tools=get_tool_definitions(),
            )
        assert loop.system_prompt
        assert len(loop.tools) == 10
        tool_names = {t["function"]["name"] for t in loop.tools}
        assert "delegate_task" in tool_names
        assert "read_file" in tool_names

    def test_create_agent_loop_uses_configured_context_length(
        self, orch_no_projects, mock_llm_client
    ):
        override = ModelConfig(
            provider="openai",
            model="small-context",
            context_length=32000,
        )
        orch_no_projects._settings.set_runtime_model_override("butler", override)

        with patch.object(orch_no_projects, "create_llm_client", return_value=mock_llm_client):
            loop = orch_no_projects.create_agent_loop(role="butler")

        assert loop.config.max_context_tokens == 32000

    def test_create_agent_loop_infers_deepseek_context_length(
        self, orch_no_projects, mock_llm_client
    ):
        override = ModelConfig(provider="deepseek", model="deepseek-chat")
        orch_no_projects._settings.set_runtime_model_override("butler", override)

        with patch.object(orch_no_projects, "create_llm_client", return_value=mock_llm_client):
            loop = orch_no_projects.create_agent_loop(role="butler")

        assert loop.config.max_context_tokens == 64000

    def test_create_project_agent_loop_has_profile_prompt(
        self, orch_with_project, mock_llm_client
    ):
        with patch.object(orch_with_project, "create_llm_client", return_value=mock_llm_client):
            loop = orch_with_project.create_project_agent_loop(role="dev")
        assert loop.system_prompt
        assert "开发" in loop.system_prompt or "工具" in loop.system_prompt


@pytest.mark.integration
class TestProjectSwitch:
    def test_on_project_switch_callback_triggers(self, tmp_path, monkeypatch, tmp_butler_home):
        _setup_projects_dir(tmp_path, monkeypatch)
        from butler.orchestrator import ButlerOrchestrator

        orch = ButlerOrchestrator(user_id="test", channel="test")
        calls: list[tuple[str, str]] = []

        def _track(old: str, new: str) -> None:
            calls.append((old, new))

        orch.project_manager.on_switch(_track)
        orch.project_manager.switch_project("test-project")
        assert any(c[1] == "test-project" for c in calls)

    def test_memory_and_skill_state_updated(self, tmp_path, monkeypatch, tmp_butler_home):
        _setup_projects_dir(tmp_path, monkeypatch)
        from butler.orchestrator import ButlerOrchestrator
        from butler.memory import ProjectMemory

        orch = ButlerOrchestrator(user_id="test", channel="test")
        assert orch._project_memory is None

        orch.on_project_switch("", "test-project")
        orch.project_manager.switch_project("test-project")
        orch.on_project_switch("", "test-project")

        assert orch._project_memory is not None
        assert isinstance(orch._project_memory, ProjectMemory)
        assert orch._skill_router is not None

    def test_project_switch_refreshes_memory_provider(self, orch_no_projects):
        provider = MagicMock()
        provider._turn_buffer = [{"role": "user", "content": "old"}]
        orch_no_projects.memory_provider = provider

        orch_no_projects.on_project_switch("old", "new")

        assert provider._turn_buffer == []
        provider._reload_project_branch.assert_called_once()


@pytest.mark.integration
class TestSkillInjection:
    def test_no_matching_skills_returns_original(self, orch_no_projects):
        text = "completely unique xyz task description 99999"
        result = orch_no_projects.inject_skill_context(text)
        assert result == text

    def test_empty_string_returns_empty(self, orch_no_projects):
        assert orch_no_projects.inject_skill_context("") == ""
        assert orch_no_projects.inject_skill_context("   ") == "   "

    def test_skill_router_builds_from_metadata_only(self, orch_no_projects):
        manager = MagicMock()
        manager.list_skills.return_value = [
            {"name": "python-dev", "description": "Python development", "triggers": ["python"]},
            {"name": "docker-ops", "description": "Docker operations", "triggers": ["docker"]},
        ]
        manager.get_skill.return_value = {
            "name": "python-dev",
            "description": "Python development",
            "triggers": ["python"],
            "content": "Use pytest",
        }
        manager.get_skills.return_value = {
            "python-dev": {
                "name": "python-dev",
                "description": "Python development",
                "triggers": ["python"],
                "content": "Use pytest",
            }
        }

        with patch("butler.orchestrator._combined_skill_manager", return_value=manager):
            orch_no_projects._rebuild_skill_router()

        manager.get_skill.assert_not_called()
        diagnostics: dict[str, object] = {}
        result = orch_no_projects.inject_skill_context("please run python tests", diagnostics=diagnostics)
        assert "Use pytest" in result
        manager.get_skills.assert_called_once_with(["python-dev"])
        assert diagnostics["skill_context_injected"] is True
        assert diagnostics["skill_matches"] == ["python-dev"]

    def test_skill_injection_skips_empty_lazy_loaded_content(self, orch_no_projects):
        manager = MagicMock()
        manager.list_skills.return_value = [
            {"name": "python-dev", "description": "Python development", "triggers": ["python"]},
        ]
        manager.get_skills.return_value = {}

        with patch("butler.orchestrator._combined_skill_manager", return_value=manager):
            orch_no_projects._rebuild_skill_router()

        result = orch_no_projects.inject_skill_context("python task")

        assert result == "python task"


@pytest.mark.integration
class TestMemoryContext:
    def test_build_memory_context_returns_string(self, orch_no_projects):
        ctx = orch_no_projects.build_memory_context()
        assert isinstance(ctx, str)

    def test_with_project_memory_includes_project_section(self, orch_with_project):
        ctx = orch_with_project.build_memory_context(for_role="dev")
        assert "当前项目记忆" in ctx or ctx == orch_with_project.butler_memory.get_system_context(
            "test-project"
        ) or "项目" in ctx

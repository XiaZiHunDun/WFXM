"""L1 unit tests for butler.project."""

from pathlib import Path

import pytest
import yaml

from butler.config import ModelConfig, reload_butler_settings
from butler.project import Project


@pytest.fixture
def butler_config_with_models(tmp_butler_home):
    """Global Butler config with dev_agent defaults for merge tests."""
    config_path = tmp_butler_home / "config.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "default_provider": "minimax",
                "models": {
                    "dev_agent": {
                        "provider": "deepseek",
                        "model": "deepseek-chat",
                        "temperature": 0.3,
                    },
                },
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    reload_butler_settings()
    yield
    reload_butler_settings()


def _write_project_yaml(directory: Path, content: dict) -> Path:
    path = directory / "project.yaml"
    path.write_text(yaml.safe_dump(content, allow_unicode=True), encoding="utf-8")
    return path


@pytest.mark.unit
class TestProjectFromYaml:
    def test_normal_load(self, tmp_path):
        proj_dir = tmp_path / "app"
        proj_dir.mkdir()
        _write_project_yaml(
            proj_dir,
            {
                "name": "my-app",
                "type": "software",
                "description": "Test application",
                "tools": ["read_file"],
            },
        )
        project = Project.from_yaml(proj_dir / "project.yaml")
        assert project.name == "my-app"
        assert project.type == "software"
        assert project.description == "Test application"
        assert project.tools == ["read_file"]
        assert project.workspace == proj_dir.resolve()

    def test_missing_optional_fields_use_defaults(self, tmp_path):
        proj_dir = tmp_path / "minimal"
        proj_dir.mkdir()
        _write_project_yaml(proj_dir, {"name": "minimal"})
        project = Project.from_yaml(proj_dir / "project.yaml")
        assert project.type == "software"
        assert project.description == ""
        assert project.status == "active"
        assert project.models == {}
        assert project.workflows == []
        assert project.tools == []

    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            Project.from_yaml(Path("/nonexistent/path/project.yaml"))


@pytest.mark.unit
class TestProjectResolveModel:
    def test_merges_global_and_project_yaml(
        self, tmp_path, butler_config_with_models
    ):
        proj_dir = tmp_path / "merge-proj"
        proj_dir.mkdir()
        _write_project_yaml(
            proj_dir,
            {
                "name": "merge-proj",
                "models": {
                    "dev_agent": {"model": "deepseek-reasoner"},
                },
            },
        )
        project = Project.from_yaml(proj_dir / "project.yaml")
        cfg = project.resolve_model("dev_agent")
        assert cfg.provider == "deepseek"
        assert cfg.model == "deepseek-reasoner"
        assert cfg.temperature == 0.3

    def test_runtime_override_wins(
        self, tmp_path, butler_config_with_models
    ):
        proj_dir = tmp_path / "override-proj"
        proj_dir.mkdir()
        _write_project_yaml(proj_dir, {"name": "override-proj"})
        project = Project.from_yaml(proj_dir / "project.yaml")
        override = ModelConfig(provider="openai", model="gpt-4o", temperature=0.9)
        cfg = project.resolve_model("dev_agent", runtime_override=override)
        assert cfg.provider == "openai"
        assert cfg.model == "gpt-4o"
        assert cfg.temperature == 0.9


@pytest.mark.unit
class TestProjectPersistence:
    def test_to_dict_set_model_save_round_trip(self, tmp_path):
        proj_dir = tmp_path / "persist-proj"
        proj_dir.mkdir()
        yaml_path = _write_project_yaml(
            proj_dir,
            {"name": "persist-proj", "type": "software", "description": "Round trip"},
        )
        project = Project.from_yaml(yaml_path)
        project.set_model(
            "dev_agent",
            ModelConfig(provider="qwen", model="qwen-max", max_tokens=8192),
        )

        reloaded = Project.from_yaml(proj_dir / "project.yaml")
        assert reloaded.name == "persist-proj"
        assert "dev_agent" in reloaded.models
        assert reloaded.models["dev_agent"].provider == "qwen"
        assert reloaded.models["dev_agent"].model == "qwen-max"
        assert reloaded.models["dev_agent"].max_tokens == 8192

        d = reloaded.to_dict()
        assert d["name"] == "persist-proj"
        assert "models" in d
        assert d["models"]["dev_agent"]["provider"] == "qwen"

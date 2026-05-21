"""Tests for butler.model_resolve (M2 effective merge + M3 /model)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from butler.config import ModelConfig, LayeredModelConfig, reload_butler_settings
from butler.model_resolve import (
    handle_model_command,
    normalize_role,
    parse_model_spec,
    resolve_effective_model,
)
from butler.project import Project
from butler.project_manager import ProjectManager


def _reset() -> None:
    ProjectManager._instance = None
    reload_butler_settings()


@pytest.mark.unit
class TestNormalizeAndParse:
    def test_aliases(self):
        assert normalize_role("dev") == "dev_agent"
        assert normalize_role("lead") == "butler"

    def test_parse_slash_and_colon(self):
        assert parse_model_spec("minimax/M2.7").provider == "minimax"
        assert parse_model_spec("deepseek:chat").model == "chat"


@pytest.mark.unit
class TestResolveEffectiveModel:
    def test_project_butler_overrides_global(self, tmp_path, monkeypatch, tmp_butler_home):
        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()
        proj_dir = projects_dir / "p1"
        proj_dir.mkdir()
        (proj_dir / "project.yaml").write_text(
            yaml.safe_dump(
                {
                    "name": "p1",
                    "models": {
                        "butler": {"provider": "qwen", "model": "qwen-max"},
                    },
                },
                allow_unicode=True,
            ),
            encoding="utf-8",
        )
        monkeypatch.setenv("BUTLER_PROJECTS_DIR", str(projects_dir))
        monkeypatch.setenv("MINIMAX_API_KEY", "k")
        _reset()
        settings = reload_butler_settings()
        project = Project.from_yaml(proj_dir / "project.yaml")

        em = resolve_effective_model("butler", project=project, settings=settings)
        assert em.config.provider == "qwen"
        assert em.config.model == "qwen-max"
        assert "project:p1" in em.sources

    def test_runtime_wins_over_project(self, tmp_path, monkeypatch, tmp_butler_home):
        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()
        proj_dir = projects_dir / "p1"
        proj_dir.mkdir()
        (proj_dir / "project.yaml").write_text(
            yaml.safe_dump({"name": "p1", "models": {"dev_agent": {"model": "from-project"}}}),
            encoding="utf-8",
        )
        monkeypatch.setenv("BUTLER_PROJECTS_DIR", str(projects_dir))
        monkeypatch.setenv("MINIMAX_API_KEY", "k")
        _reset()
        settings = reload_butler_settings()
        project = Project.from_yaml(proj_dir / "project.yaml")
        settings.set_runtime_model_override(
            "dev_agent",
            ModelConfig(provider="openai", model="gpt-4o"),
        )

        em = resolve_effective_model("dev_agent", project=project, settings=settings)
        assert em.config.model == "gpt-4o"
        assert "runtime" in em.sources


@pytest.mark.unit
class TestHandleModelCommand:
    def test_list_includes_effective_header(self, tmp_butler_home, monkeypatch):
        monkeypatch.setenv("MINIMAX_API_KEY", "k")
        _reset()
        text, reset = handle_model_command("")
        assert "当前有效模型" in text
        assert reset is False

    def test_save_butler_persists_yaml(self, tmp_butler_home, monkeypatch):
        monkeypatch.setenv("MINIMAX_API_KEY", "k")
        _reset()
        settings = reload_butler_settings()
        text, reset = handle_model_command(
            "save butler deepseek/deepseek-chat",
            settings=settings,
        )
        assert "持久化" in text
        assert reset is True
        assert settings.models.butler.model == "deepseek-chat"
        raw = yaml.safe_load(settings.config_yaml_path.read_text(encoding="utf-8"))
        assert raw["models"]["butler"]["model"] == "deepseek-chat"

    def test_save_dev_requires_project(self, tmp_butler_home, monkeypatch):
        monkeypatch.setenv("MINIMAX_API_KEY", "k")
        _reset()
        settings = reload_butler_settings()
        text, _ = handle_model_command("save dev_agent qwen/qwen-max", settings=settings)
        assert "切换" in text

    def test_temporary_override(self, tmp_butler_home, monkeypatch):
        monkeypatch.setenv("MINIMAX_API_KEY", "k")
        _reset()
        settings = reload_butler_settings()
        text, reset = handle_model_command("butler openai/gpt-4o", settings=settings)
        assert "临时" in text
        assert reset is True
        em = resolve_effective_model("butler", settings=settings)
        assert em.config.model == "gpt-4o"

    def test_reset_clears_runtime(self, tmp_butler_home, monkeypatch):
        monkeypatch.setenv("MINIMAX_API_KEY", "k")
        _reset()
        settings = reload_butler_settings()
        handle_model_command("butler openai/gpt-4o", settings=settings)
        text, _ = handle_model_command("reset butler", settings=settings)
        assert "清除" in text
        assert "butler" not in settings._runtime_model_overrides

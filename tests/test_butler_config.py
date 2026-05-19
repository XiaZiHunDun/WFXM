"""Tests for butler.config — ModelConfig, LayeredModelConfig, ButlerSettings."""

import os
import tempfile
from pathlib import Path

import pytest
import yaml

from butler.config import (
    ButlerSettings,
    LayeredModelConfig,
    ModelConfig,
    get_butler_settings,
    reload_butler_settings,
)


class TestModelConfig:
    def test_empty(self):
        mc = ModelConfig()
        assert mc.is_empty()
        assert mc.to_dict() == {}

    def test_merge_with_override(self):
        base = ModelConfig(provider="minimax", model="M2.7")
        override = ModelConfig(model="M2.7-pro")
        merged = base.merge_with(override)
        assert merged.provider == "minimax"
        assert merged.model == "M2.7-pro"

    def test_merge_with_none(self):
        base = ModelConfig(provider="openai", model="gpt-4o", temperature=0.7)
        merged = base.merge_with(None)
        assert merged.provider == "openai"
        assert merged.temperature == 0.7

    def test_from_dict_empty(self):
        mc = ModelConfig.from_dict(None)
        assert mc.is_empty()

    def test_from_dict(self):
        mc = ModelConfig.from_dict({"provider": "deepseek", "model": "deepseek-chat", "temperature": 0.5})
        assert mc.provider == "deepseek"
        assert mc.model == "deepseek-chat"
        assert mc.temperature == 0.5

    def test_roundtrip(self):
        mc = ModelConfig(provider="qwen", model="qwen-max", max_tokens=4096, context_length=32768)
        d = mc.to_dict()
        mc2 = ModelConfig.from_dict(d)
        assert mc2.provider == mc.provider
        assert mc2.model == mc.model
        assert mc2.max_tokens == mc.max_tokens
        assert mc2.context_length == mc.context_length


class TestLayeredModelConfig:
    def test_defaults(self):
        lmc = LayeredModelConfig()
        assert lmc.butler.is_empty()
        assert lmc.dev_agent.is_empty()

    def test_get_set(self):
        lmc = LayeredModelConfig()
        lmc.set("butler", ModelConfig(provider="minimax", model="M2.7"))
        assert lmc.get("butler").provider == "minimax"

    def test_unknown_role_returns_butler(self):
        lmc = LayeredModelConfig(butler=ModelConfig(provider="test"))
        assert lmc.get("unknown_role").provider == "test"

    def test_roundtrip(self):
        lmc = LayeredModelConfig(
            butler=ModelConfig(provider="minimax", model="M2.7"),
            dev_agent=ModelConfig(provider="deepseek", model="chat"),
        )
        d = lmc.to_dict()
        lmc2 = LayeredModelConfig.from_dict(d)
        assert lmc2.butler.provider == "minimax"
        assert lmc2.dev_agent.provider == "deepseek"


class TestButlerSettings:
    def test_env_providers(self, monkeypatch):
        monkeypatch.setenv("MINIMAX_API_KEY", "test-key")
        monkeypatch.setenv("MINIMAX_MODEL", "test-model")
        with tempfile.TemporaryDirectory() as td:
            monkeypatch.setenv("BUTLER_HOME", td)
            s = ButlerSettings()
            assert "minimax" in s.providers
            assert s.providers["minimax"].api_key == "test-key"

    def test_get_model_config_3layer(self, monkeypatch):
        monkeypatch.setenv("MINIMAX_API_KEY", "k")
        with tempfile.TemporaryDirectory() as td:
            monkeypatch.setenv("BUTLER_HOME", td)
            s = ButlerSettings(default_provider="minimax")
            mc = s.get_model_config("butler")
            assert mc.provider == "minimax"

            s.set_runtime_model_override("butler", ModelConfig(model="overridden"))
            mc2 = s.get_model_config("butler")
            assert mc2.model == "overridden"

            s.clear_runtime_model_overrides()
            mc3 = s.get_model_config("butler")
            assert mc3.model != "overridden"

    def test_save_load(self, monkeypatch):
        with tempfile.TemporaryDirectory() as td:
            monkeypatch.setenv("BUTLER_HOME", td)
            monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
            s = ButlerSettings(butler_name="TestButler", owner_name="TestOwner")
            s.models = LayeredModelConfig(butler=ModelConfig(provider="test", model="test-m"))
            s.save_butler_config()

            with open(Path(td) / "config.yaml", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            assert data["butler_name"] == "TestButler"

            s2 = ButlerSettings.load(Path(td) / "config.yaml")
            assert s2.butler_name == "TestButler"
            assert s2.models.butler.provider == "test"


class TestProjectManager:
    def test_list_and_switch(self, monkeypatch):
        monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
        with tempfile.TemporaryDirectory() as td:
            monkeypatch.setenv("BUTLER_HOME", td)
            projects_dir = Path(td) / "projects"
            projects_dir.mkdir()
            p1 = projects_dir / "TestProj"
            p1.mkdir()
            (p1 / "project.yaml").write_text(
                yaml.safe_dump({"name": "TestProj", "type": "software", "description": "test"})
            )

            from butler.project_manager import ProjectManager
            ProjectManager._instance = None
            pm = ProjectManager(projects_dir)
            assert len(pm.list_projects()) == 1
            assert pm.switch_project("TestProj")
            assert pm.current_project == "TestProj"
            assert pm.get_current().name == "TestProj"
            ProjectManager._instance = None

    def test_create_project(self, monkeypatch):
        monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
        with tempfile.TemporaryDirectory() as td:
            monkeypatch.setenv("BUTLER_HOME", td)
            projects_dir = Path(td) / "projects"
            projects_dir.mkdir()

            from butler.project_manager import ProjectManager
            ProjectManager._instance = None
            pm = ProjectManager(projects_dir)
            proj = pm.create_project("NewProject", "software", "A new project")
            assert proj is not None
            assert proj.name == "NewProject"
            assert (projects_dir / "NewProject" / "project.yaml").exists()
            ProjectManager._instance = None

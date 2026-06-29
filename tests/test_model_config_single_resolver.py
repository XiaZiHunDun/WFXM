"""Single-resolver consistency: get_model_config vs resolve_effective_model."""

from __future__ import annotations

import pathlib

import yaml

import pytest

from butler.config import ModelConfig, reload_butler_settings
from butler.core.model_context import resolve_max_output_tokens
from butler.model_resolve import resolve_effective_model
from butler.project import Project
from butler.transport.fallback import build_fallback_chain


def _reset() -> None:
    from butler.project.manager import ProjectManager

    ProjectManager._instance = None
    reload_butler_settings()


@pytest.mark.unit
class TestSingleResolver:
    def test_get_model_config_matches_resolve_with_project(
        self, tmp_path, monkeypatch, tmp_butler_home
    ):
        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()
        proj_dir = projects_dir / "p1"
        proj_dir.mkdir()
        (proj_dir / "project.yaml").write_text(
            yaml.safe_dump(
                {
                    "name": "p1",
                    "models": {
                        "butler": {
                            "provider": "deepseek",
                            "model": "deepseek-chat",
                            "max_tokens": 8192,
                        },
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
        mc = settings.get_model_config("butler", project=project)
        assert mc.provider == em.config.provider == "deepseek"
        assert mc.model == em.config.model == "deepseek-chat"
        assert mc.max_tokens == 8192

    def test_model_context_max_tokens_uses_project_layer(
        self, tmp_path, monkeypatch, tmp_butler_home
    ):
        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()
        proj_dir = projects_dir / "p1"
        proj_dir.mkdir()
        (proj_dir / "project.yaml").write_text(
            yaml.safe_dump(
                {
                    "name": "p1",
                    "models": {"butler": {"provider": "minimax", "model": "M2", "max_tokens": 6000}},
                },
                allow_unicode=True,
            ),
            encoding="utf-8",
        )
        monkeypatch.setenv("BUTLER_PROJECTS_DIR", str(projects_dir))
        monkeypatch.setenv("MINIMAX_API_KEY", "k")
        _reset()

        class _PM:
            def resolve_active_project_name(self, *, session_key: str = "") -> str:
                return "p1"

            def get_current(self, *, session_key: str = ""):
                return Project.from_yaml(proj_dir / "project.yaml")

        class _Orch:
            project_manager = _PM()

        assert resolve_max_output_tokens(_Orch(), session_key="sk") == 6000

    def test_llm_fallback_disabled(self, monkeypatch, tmp_butler_home):
        monkeypatch.setenv("MINIMAX_API_KEY", "k")
        monkeypatch.setenv("DEEPSEEK_API_KEY", "d")
        _reset()
        settings = reload_butler_settings()
        settings.llm_fallback = {"enabled": False}
        primary = ModelConfig(provider="minimax", model="MiniMax-M2.7")
        chain = build_fallback_chain(primary)
        assert len(chain) == 1
        assert chain[0].provider == "minimax"

    def test_embedding_yaml_before_env(self, monkeypatch, tmp_butler_home):
        monkeypatch.delenv("BUTLER_EMBEDDING_PROVIDER", raising=False)
        monkeypatch.delenv("BUTLER_EMBEDDING_MODEL", raising=False)
        _reset()
        settings = reload_butler_settings()
        settings.embedding = {
            "provider": "fastembed",
            "model": "BAAI/bge-small-en-v1.5",
        }
        from butler.model_resolve import resolve_embedding_config

        assert resolve_embedding_config() == ("fastembed", "BAAI/bge-small-en-v1.5")


def test_business_code_does_not_import_get_model_config():
    """PROD-P6-07: ``get_model_config`` is only the config.py thin wrapper."""
    allowlist = frozenset({"butler/config.py"})
    offenders: list[str] = []
    for path in sorted(pathlib.Path("butler").rglob("*.py")):
        rel = path.as_posix()
        if rel in allowlist:
            continue
        if "get_model_config" in path.read_text(encoding="utf-8"):
            offenders.append(rel)
    assert not offenders, (
        "Use resolve_effective_model / resolve_*_config instead:\n"
        + "\n".join(offenders)
    )


def test_model_resolve_reexports_auxiliary_and_embedding():
    from butler.model_resolve import resolve_auxiliary_config, resolve_embedding_config

    assert callable(resolve_auxiliary_config)
    assert callable(resolve_embedding_config)

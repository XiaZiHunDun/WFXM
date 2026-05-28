"""Model resolution uses single path for orchestrator credentials."""

from butler.config import reload_butler_settings
from butler.model_resolve import resolve_effective_model
from butler.orchestrator import ButlerOrchestrator
from butler.project.manager import ProjectManager


def test_butler_credentials_match_project_dev_agent(tmp_path, monkeypatch):
    ws = tmp_path / "proj"
    ws.mkdir()
    (ws / "project.yaml").write_text(
        f"name: TestProj\ntype: software\nworkspace: {ws}\n"
        "models:\n  dev_agent:\n    provider: deepseek\n    model: deepseek-chat\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("BUTLER_PROJECTS_DIR", str(tmp_path))
    ProjectManager._instance = None  # type: ignore[misc]
    reload_butler_settings()
    orch = ButlerOrchestrator(user_id="u1", channel="cli")
    pm = orch.project_manager
    pm._scan_projects()
    pm.switch_project("TestProj")

    em = resolve_effective_model(
        "dev_agent",
        project=pm.get_current(),
        settings=orch._settings,
    )
    creds = orch._model_credentials("dev_agent")
    assert creds.get("provider") == "deepseek"
    assert em.config.provider == "deepseek"

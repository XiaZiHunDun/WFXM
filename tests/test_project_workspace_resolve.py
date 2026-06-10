"""Project workspace resolution when session key slug is sanitized."""

from __future__ import annotations

from pathlib import Path

from butler.project.manager import ProjectManager
from butler.project.model import Project


def test_resolve_falls_back_to_chat_map_when_slug_corrupt(tmp_path):
    ProjectManager._instance = None
    pm = ProjectManager(projects_dir=tmp_path / "projects")
    ws = tmp_path / "workspace"
    ws.mkdir()
    pm._projects["灵文1号"] = Project(
        name="灵文1号",
        type="content",
        description="test",
        workspace=ws,
    )
    pm.switch_project_for_chat(platform="wechat", chat_id="u1", name="灵文1号")

    # Sanitized key loses CJK — slug segment no longer matches registry.
    sk = "wechat:u1:____1__"
    proj = pm.get_current(session_key=sk)
    assert proj is not None
    assert proj.name == "灵文1号"
    assert Path(proj.workspace) == ws

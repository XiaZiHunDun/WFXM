"""D #2: `/工作流 list` 微信口径应展示 workflow_state 当前阶段。

Aligns with builtin:workflow_state_digest in
butler/runtime/builtin_handlers.py:26 so 微信口径与
factory-status-daily 摘要字段一致。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from butler.project import Project
from butler.workflows.loader import format_workflows_for_wechat


def _project_with_workflow(tmp_path: Path, folder: str = "ling") -> Project:
    proj_dir = tmp_path / folder
    proj_dir.mkdir(parents=True)
    (proj_dir / "project.yaml").write_text(
        yaml.safe_dump(
            {
                "name": folder,
                "type": "content",
                "description": "灵文1号",
                "workspace": str(proj_dir),
                "workflows": [
                    {"name": "novel-factory", "description": "小说流水线"},
                ],
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    return Project.from_yaml(proj_dir / "project.yaml")


def _write_workflow_state(
    workspace: Path,
    *,
    phase: str = "draft",
    step: str = "draft-1",
    pname: str = "灵文1号",
    pphase: str = "drafting",
) -> Path:
    state_path = workspace / "novel-factory" / "workflow_state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(
            {
                "current_phase": phase,
                "current_step": step,
                "project_status": {"name": pname, "phase": pphase},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return state_path


@pytest.mark.unit
class TestWechatWorkflowStateHeader:
    def test_includes_workflow_state_when_present(self, tmp_path):
        proj = _project_with_workflow(tmp_path)
        _write_workflow_state(proj.workspace)

        out = format_workflows_for_wechat(proj)

        assert "项目: 灵文1号" in out
        assert "current_phase: draft" in out
        assert "current_step: draft-1" in out
        assert "project_status.phase: drafting" in out
        # Header precedes workflow list (verify ordering).
        assert out.index("项目: 灵文1号") < out.index("工作流列表：")

    def test_no_header_when_workflow_state_missing(self, tmp_path):
        proj = _project_with_workflow(tmp_path)

        out = format_workflows_for_wechat(proj)

        assert "current_phase" not in out
        assert "project_status" not in out
        assert "工作流列表：" in out
        assert "novel-factory" in out

    def test_no_header_on_corrupt_workflow_state_json(self, tmp_path):
        proj = _project_with_workflow(tmp_path)
        state_dir = proj.workspace / "novel-factory"
        state_dir.mkdir(parents=True, exist_ok=True)
        (state_dir / "workflow_state.json").write_text(
            "{not valid json", encoding="utf-8"
        )

        out = format_workflows_for_wechat(proj)

        # Graceful degrade: list still rendered, no header crash.
        assert "current_phase" not in out
        assert "工作流列表：" in out
        assert "novel-factory" in out

    def test_no_project_returns_empty_message(self, tmp_path):
        out = format_workflows_for_wechat(None)
        assert "未配置工作流" in out
        # No workflow_state probe without a project.
        assert "current_phase" not in out
"""Tests for butler.runtime (phase 3a)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from butler.config import reload_butler_settings
from butler.project import Project
from butler.project_manager import ProjectManager
from butler.runtime import audit, loader, schedule, service
from butler.runtime.builtin_handlers import run_builtin


def _reset() -> None:
    ProjectManager._instance = None
    reload_butler_settings()


def _write_jobs(ws: Path, jobs: list[dict]) -> None:
    rt = ws / "runtime"
    rt.mkdir(parents=True, exist_ok=True)
    (rt / "jobs.yaml").write_text(
        yaml.safe_dump(
            {"version": 1, "project": "test", "jobs": jobs},
            allow_unicode=True,
        ),
        encoding="utf-8",
    )


@pytest.fixture
def runtime_project(tmp_path, monkeypatch):
    _reset()
    monkeypatch.setenv("BUTLER_PROJECTS_DIR", str(tmp_path / "projects"))
    ws = tmp_path / "projects" / "TestProj"
    ws.mkdir(parents=True)
    (ws / "project.yaml").write_text(
        yaml.safe_dump({"name": "TestProj", "type": "novel"}),
        encoding="utf-8",
    )
    bh = tmp_path / "butler_home"
    bh.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("BUTLER_HOME", str(bh))
    reload_butler_settings()
    pm = ProjectManager()
    pm._scan_projects()
    return ws, pm


def test_load_jobs_and_find(runtime_project):
    ws, _ = runtime_project
    _write_jobs(
        ws,
        [
            {
                "id": "demo",
                "mode": "readonly",
                "enabled": True,
                "handler": "builtin:workflow_state_digest",
            }
        ],
    )
    job = loader.find_job(ws, "demo")
    assert job is not None
    assert job.is_builtin


def test_builtin_workflow_digest(runtime_project):
    ws, _ = runtime_project
    nf = ws / "novel-factory"
    nf.mkdir()
    (nf / "workflow_state.json").write_text(
        json.dumps(
            {
                "current_phase": "P1",
                "current_step": "S2",
                "project_status": {"name": "灵文", "phase": "draft"},
            }
        ),
        encoding="utf-8",
    )
    out = run_builtin("builtin:workflow_state_digest", ws)
    assert out["success"] is True
    assert "P1" in out["summary"]


def test_run_readonly_job_mock_notify(runtime_project, monkeypatch):
    ws, pm = runtime_project
    _write_jobs(
        ws,
        [
            {
                "id": "echo",
                "mode": "readonly",
                "enabled": True,
                "command": ["echo", "hello-runtime"],
            },
            {
                "id": "mut",
                "mode": "mutating",
                "enabled": True,
                "command": ["echo", "no"],
            },
        ],
    )
    monkeypatch.setenv("BUTLER_RUNTIME_ENABLED", "1")
    with patch("butler.runtime.service._maybe_notify"):
        r = service.run_job("TestProj", "echo", skip_notify=True)
    assert r["success"] is True
    assert "hello-runtime" in (r.get("summary") or "")

    bad = service.run_job("TestProj", "mut", skip_notify=True)
    assert bad.get("error")
    assert "批准" in bad["error"] or "改盘" in bad["error"]


def test_disabled_job(runtime_project):
    ws, _ = runtime_project
    _write_jobs(
        ws,
        [
            {
                "id": "off",
                "mode": "readonly",
                "enabled": False,
                "command": ["echo", "x"],
            }
        ],
    )
    r = service.run_job("TestProj", "off", skip_notify=True)
    assert "禁用" in (r.get("error") or "")


def test_schedule_empty_not_due():
    assert schedule.job_is_due("") is False
    assert schedule.format_schedule_hint("") == "（手动）"


def test_format_jobs_list(runtime_project):
    ws, _ = runtime_project
    _write_jobs(
        ws,
        [{"id": "a", "description": "desc", "mode": "readonly", "enabled": True}],
    )
    text = service.format_jobs_list_text("TestProj")
    assert "a" in text
    assert "desc" in text


def test_approve_mutating_one_shot(runtime_project, monkeypatch):
    ws, _ = runtime_project
    _write_jobs(
        ws,
        [
            {
                "id": "mut",
                "mode": "mutating",
                "enabled": True,
                "command": ["echo", "approved-mut"],
                "approval": {"required": True, "expires_hours": 1},
            }
        ],
    )
    monkeypatch.setenv("BUTLER_RUNTIME_ENABLED", "1")
    with patch("butler.runtime.service._maybe_notify"):
        denied = service.run_job("TestProj", "mut", skip_notify=True)
    assert denied.get("error")

    from butler.runtime import approval

    with patch("butler.runtime.service._maybe_notify"):
        out = service.approve_and_run("TestProj", "mut", run_now=True)
    assert out.get("success") is True
    assert not approval.is_approved("TestProj", "mut")


def test_audit_latest(runtime_project):
    ws, _ = runtime_project
    audit.write_run_record(
        project_name="TestProj",
        job_id="a",
        payload={"success": True, "finished_at": "t1"},
    )
    last = audit.latest_run("TestProj", "a")
    assert last is not None
    assert last.get("success") is True

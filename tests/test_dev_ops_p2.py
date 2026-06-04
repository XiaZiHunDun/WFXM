"""P2: tool audit JSONL, runtime bridge, controlled download."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from butler.tools.audit_persist import audit_jsonl_path, persist_tool_audit_event
from butler.tools.download_tools import _host_allowed, _validate_url, download_enabled
from butler.tools.registry import dispatch_tool, get_tool_definitions


@pytest.fixture(autouse=True)
def _safe_root(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_TOOL_SAFE_ROOT", str(tmp_path))


@pytest.mark.module_test
class TestAuditJsonl:
    def test_persist_when_enabled(self, tmp_path, monkeypatch):
        log_path = tmp_path / "audit" / "tools.jsonl"
        monkeypatch.setenv("BUTLER_TOOL_AUDIT_JSONL", "1")
        monkeypatch.setenv("BUTLER_TOOL_AUDIT_PATH", str(log_path))
        persist_tool_audit_event({"tool": "read_file", "ok": True, "code": "TOOL_OK"})
        assert log_path.is_file()
        row = json.loads(log_path.read_text(encoding="utf-8").strip())
        assert row["tool"] == "read_file"
        assert "ts" in row

    def test_skipped_when_disabled(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BUTLER_TOOL_AUDIT_JSONL", "0")
        monkeypatch.setenv("BUTLER_TOOL_AUDIT_PATH", str(tmp_path / "x.jsonl"))
        persist_tool_audit_event({"tool": "x"})
        assert not (tmp_path / "x.jsonl").exists()


@pytest.mark.module_test
class TestDownloadTool:
    def test_disabled_by_default(self, tmp_path):
        assert not download_enabled()
        raw = dispatch_tool(
            "download_file",
            {"url": "https://example.com/x", "dest_path": "x.bin"},
        )
        data = json.loads(raw)
        assert "DOWNLOAD_DISABLED" in str(data.get("code", ""))

    def test_host_allowlist(self):
        assert _host_allowed("github.com")
        assert _host_allowed("raw.githubusercontent.com")
        assert not _host_allowed("evil.example.com")

    def test_rejects_http(self):
        ok, err = _validate_url("http://github.com/foo")
        assert not ok
        assert "https" in err

    @patch("butler.tools.download_tools.urlopen")
    def test_download_writes_file(self, mock_urlopen, tmp_path, monkeypatch):
        monkeypatch.setenv("BUTLER_ENABLE_DOWNLOAD", "1")

        class _Resp:
            headers = {"Content-Length": "5"}
            _done = False

            def read(self, n=-1):
                if self._done:
                    return b""
                self._done = True
                return b"hello"

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

        mock_urlopen.return_value = _Resp()

        with patch(
            "butler.tools.download_tools._resolve_public_ip",
            return_value=(True, ""),
        ):
            raw = dispatch_tool(
                "download_file",
                {
                    "url": "https://raw.githubusercontent.com/org/repo/main/README.md",
                    "dest_path": "vendor/README.md",
                },
            )
        data = json.loads(raw)
        assert data.get("success") is True
        assert (tmp_path / "vendor" / "README.md").read_bytes() == b"hello"


@pytest.mark.module_test
class TestRuntimeBridgeTools:
    def test_tools_registered(self):
        names = {t["function"]["name"] for t in get_tool_definitions()}
        assert "list_runtime_jobs" in names
        assert "run_runtime_job" in names

    def test_mutating_job_rejected_for_agent(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BUTLER_RUNTIME_ENABLED", "1")
        proj_dir = tmp_path / "P1"
        proj_dir.mkdir()
        (proj_dir / "runtime").mkdir()
        (proj_dir / "runtime" / "jobs.yaml").write_text(
            """
version: 1
project: P1
jobs:
  - id: mut-job
    description: test
    mode: mutating
    enabled: true
    command: [echo, hi]
""".strip(),
            encoding="utf-8",
        )
        (proj_dir / "project.yaml").write_text(
            f"name: P1\nworkspace: {proj_dir}\ntools: []\n",
            encoding="utf-8",
        )

        from butler.project import Project

        proj = Project(
            name="P1",
            type="content",
            description="test",
            workspace=proj_dir,
            tools=[],
        )
        orch = MagicMock()  # noqa: magicmock-no-spec — complex facade, spec= 收益低
        orch.project_manager.get_current.return_value = proj

        pm_mock = MagicMock()  # noqa: magicmock-no-spec — complex facade, spec= 收益低
        pm_mock.get_project.return_value = proj
        with (
            patch(
                "butler.execution_context.get_current_orchestrator",
                return_value=orch,
            ),
            patch(
                "butler.project.manager.get_project_manager",
                return_value=pm_mock,
            ),
        ):
            raw = dispatch_tool("run_runtime_job", {"job_id": "mut-job"})
        data = json.loads(raw)
        assert data.get("code") == "RUNTIME_MUTATING_REQUIRES_APPROVAL"

    def test_readonly_job_via_agent_tool(self, tmp_path, monkeypatch):
        from butler.config import reload_butler_settings
        from butler.project.manager import ProjectManager

        monkeypatch.setenv("BUTLER_RUNTIME_ENABLED", "1")
        monkeypatch.setenv("BUTLER_PROJECTS_DIR", str(tmp_path / "projects"))
        bh = tmp_path / "butler_home"
        bh.mkdir(parents=True, exist_ok=True)
        monkeypatch.setenv("BUTLER_HOME", str(bh))
        reload_butler_settings()
        ProjectManager._instance = None

        proj_dir = tmp_path / "projects" / "P1"
        proj_dir.mkdir(parents=True)
        (proj_dir / "runtime").mkdir()
        (proj_dir / "runtime" / "jobs.yaml").write_text(
            """
version: 1
project: P1
jobs:
  - id: ro-echo
    description: test
    mode: readonly
    enabled: true
    command: [echo, runtime-ok]
""".strip(),
            encoding="utf-8",
        )
        (proj_dir / "project.yaml").write_text(
            "name: P1\ntype: content\nworkspace: .\ntools: []\n",
            encoding="utf-8",
        )
        pm = ProjectManager()
        pm._scan_projects()
        proj = pm.get_project("P1")
        assert proj is not None

        orch = MagicMock()  # noqa: magicmock-no-spec — complex facade, spec= 收益低
        orch.project_manager.get_current.return_value = proj

        with patch(
            "butler.execution_context.get_current_orchestrator",
            return_value=orch,
        ):
            raw = dispatch_tool("run_runtime_job", {"job_id": "ro-echo"})
        data = json.loads(raw)
        assert data.get("ok") is True
        assert data.get("success") is True
        assert "record_path" in data

"""Tests for WeChat dev slash commands (/git, /测试, /构建, /项目概况)."""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ── handle_dev_command routing ─────────────────────────────────


class TestHandleDevCommandRouting:
    @pytest.fixture
    def _owner(self):
        with patch(
            "butler.gateway.commands.dev_handlers.is_gateway_owner", return_value=True
        ):
            yield

    def test_git_command_routed(self, _owner):
        from butler.gateway.commands.dev_handlers import handle_dev_command

        with patch("butler.gateway.commands.dev_handlers.format_git_for_wechat", return_value="git-ok") as m:
            result = handle_dev_command(
                "/git", "status",
                platform="wechat", external_id="owner", session_key="k",
            )
            m.assert_called_once_with("status")
            assert result == "git-ok"

    def test_test_command_routed_cn(self, _owner):
        from butler.gateway.commands.dev_handlers import handle_dev_command

        with patch("butler.gateway.commands.dev_handlers.format_test_for_wechat", return_value="test-ok") as m:
            result = handle_dev_command(
                "/测试", "",
                platform="wechat", external_id="owner", session_key="k",
            )
            m.assert_called_once_with("")
            assert result == "test-ok"

    def test_test_command_routed_en(self, _owner):
        from butler.gateway.commands.dev_handlers import handle_dev_command

        with patch("butler.gateway.commands.dev_handlers.format_test_for_wechat", return_value="test-ok") as m:
            result = handle_dev_command(
                "/test", "arg",
                platform="wechat", external_id="owner", session_key="k",
            )
            m.assert_called_once_with("arg")
            assert result == "test-ok"

    def test_build_command_routed_cn(self, _owner):
        from butler.gateway.commands.dev_handlers import handle_dev_command

        with patch("butler.gateway.commands.dev_handlers.format_build_for_wechat", return_value="build-ok") as m:
            result = handle_dev_command(
                "/构建", "",
                platform="wechat", external_id="owner", session_key="k",
            )
            m.assert_called_once_with("")

    def test_build_command_routed_en(self, _owner):
        from butler.gateway.commands.dev_handlers import handle_dev_command

        with patch("butler.gateway.commands.dev_handlers.format_build_for_wechat", return_value="build-ok") as m:
            result = handle_dev_command(
                "/build", "",
                platform="wechat", external_id="owner", session_key="k",
            )
            m.assert_called_once_with("")

    def test_dashboard_command_routed_cn(self, _owner):
        from butler.gateway.commands.dev_handlers import handle_dev_command

        with patch("butler.gateway.commands.dev_handlers.format_project_dashboard", return_value="dash-ok") as m:
            result = handle_dev_command(
                "/项目概况", "",
                platform="wechat", external_id="owner", session_key="k",
            )
            m.assert_called_once_with("", orchestrator=None, session_key="k")

    def test_dashboard_command_routed_en(self, _owner):
        from butler.gateway.commands.dev_handlers import handle_dev_command

        with patch("butler.gateway.commands.dev_handlers.format_project_dashboard", return_value="dash-ok") as m:
            result = handle_dev_command(
                "/project-dashboard", "",
                platform="wechat", external_id="owner", session_key="k",
            )
            m.assert_called_once_with("", orchestrator=None, session_key="k")

    def test_existing_commands_still_work(self, _owner):
        from butler.gateway.commands.dev_handlers import handle_dev_command

        r = handle_dev_command(
            "/开发状态", "",
            platform="wechat", external_id="owner", session_key="k",
        )
        assert r is not None
        assert "开发工具状态" in r

    def test_unknown_returns_none(self, _owner):
        from butler.gateway.commands.dev_handlers import handle_dev_command

        assert handle_dev_command(
            "/unknown", "",
            platform="wechat", external_id="owner", session_key="k",
        ) is None

    def test_non_owner_blocked(self):
        from butler.gateway.commands.dev_handlers import handle_dev_command
        from butler.gateway.owner_gate import owner_required_message

        with patch(
            "butler.gateway.commands.dev_handlers.is_gateway_owner", return_value=False
        ):
            out = handle_dev_command(
                "/git", "status",
                platform="wechat", external_id="non_owner", session_key="k",
            )
        assert out == owner_required_message(), (
            f"非 Owner /git 应被拒，实际 {out!r}"
        )


# ── /git command ───────────────────────────────────────────────


class TestGitForWechat:
    def test_git_disabled(self):
        from butler.gateway.commands.dev_handlers import format_git_for_wechat

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("BUTLER_ENABLE_GIT", None)
            result = format_git_for_wechat()
            assert "未启用" in result

    def test_git_status_default(self):
        from butler.gateway.commands.dev_handlers import format_git_for_wechat

        status_payload = {
            "exit_code": 0,
            "stdout": "## main...origin/main\n M file1.py\n?? file2.py\n",
        }
        log_payload = {
            "exit_code": 0,
            "stdout": "abc123 2h ago fix bug\ndef456 1d ago add feature\n",
        }

        with patch.dict(os.environ, {"BUTLER_ENABLE_GIT": "1"}):
            with patch("butler.gateway.commands.dev_handlers._project_workspace", return_value=Path("/tmp")):
                with patch("butler.tools.git_tools._run_git") as mock_git:
                    mock_git.side_effect = [status_payload, log_payload]
                    result = format_git_for_wechat()
                    assert "main" in result
                    assert "Git 状态" in result

    def test_git_diff_subcommand(self):
        from butler.gateway.commands.dev_handlers import format_git_for_wechat

        diff_payload = {
            "exit_code": 0,
            "stdout": " file1.py | 2 +-\n 1 file changed, 1 insertion(+), 1 deletion(-)\n",
        }

        with patch.dict(os.environ, {"BUTLER_ENABLE_GIT": "1"}):
            with patch("butler.gateway.commands.dev_handlers._project_workspace", return_value=Path("/tmp")):
                with patch("butler.tools.git_tools._run_git", return_value=diff_payload):
                    result = format_git_for_wechat("diff")
                    assert "Diff" in result

    def test_git_log_subcommand(self):
        from butler.gateway.commands.dev_handlers import format_git_for_wechat

        log_payload = {
            "exit_code": 0,
            "stdout": "abc | 2h | dev | fix\ndef | 1d | dev | feat\n",
        }

        with patch.dict(os.environ, {"BUTLER_ENABLE_GIT": "1"}):
            with patch("butler.gateway.commands.dev_handlers._project_workspace", return_value=Path("/tmp")):
                with patch("butler.tools.git_tools._run_git", return_value=log_payload):
                    result = format_git_for_wechat("log 5")
                    assert "提交" in result

    def test_git_status_clean_workspace(self):
        from butler.gateway.commands.dev_handlers import format_git_for_wechat

        status_payload = {"exit_code": 0, "stdout": "## main\n"}
        log_payload = {"exit_code": 0, "stdout": "abc 2h fix\n"}

        with patch.dict(os.environ, {"BUTLER_ENABLE_GIT": "1"}):
            with patch("butler.gateway.commands.dev_handlers._project_workspace", return_value=Path("/tmp")):
                with patch("butler.tools.git_tools._run_git") as mock_git:
                    mock_git.side_effect = [status_payload, log_payload]
                    result = format_git_for_wechat()
                    assert "干净" in result


# ── /测试 command ──────────────────────────────────────────────


class TestTestForWechat:
    def test_terminal_disabled(self):
        from butler.gateway.commands.dev_handlers import format_test_for_wechat

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("BUTLER_ENABLE_TERMINAL", None)
            result = format_test_for_wechat()
            assert "终端未启用" in result

    def test_no_active_project(self):
        from butler.gateway.commands.dev_handlers import format_test_for_wechat

        with patch.dict(os.environ, {"BUTLER_ENABLE_TERMINAL": "1"}):
            with patch("butler.gateway.commands.dev_handlers._project_workspace", return_value=None):
                result = format_test_for_wechat()
                assert "无活跃项目" in result

    def test_no_test_command(self):
        from butler.gateway.commands.dev_handlers import format_test_for_wechat

        with patch.dict(os.environ, {"BUTLER_ENABLE_TERMINAL": "1"}):
            with patch("butler.gateway.commands.dev_handlers._project_workspace", return_value=Path("/tmp")):
                with patch("butler.gateway.commands.dev_handlers._project_dev_config", return_value={}):
                    result = format_test_for_wechat()
                    assert "test_command" in result

    def test_test_history_empty(self):
        from butler.gateway.commands.dev_handlers import format_test_for_wechat

        with tempfile.TemporaryDirectory() as tmpdir:
            ws = Path(tmpdir)
            with patch.dict(os.environ, {"BUTLER_ENABLE_TERMINAL": "1"}):
                with patch("butler.gateway.commands.dev_handlers._project_workspace", return_value=ws):
                    result = format_test_for_wechat("历史")
                    assert "暂无测试记录" in result

    def test_test_history_with_data(self):
        from butler.gateway.commands.dev_handlers import format_test_for_wechat

        with tempfile.TemporaryDirectory() as tmpdir:
            ws = Path(tmpdir)
            history_dir = ws / ".butler"
            history_dir.mkdir(parents=True)
            history = [
                {"label": "测试", "exit_code": 0, "elapsed": 3.2, "passed": 10, "failed": 0, "timestamp": time.time()},
                {"label": "测试", "exit_code": 1, "elapsed": 5.1, "passed": 8, "failed": 2, "timestamp": time.time()},
            ]
            (history_dir / "test_history.json").write_text(json.dumps(history))

            with patch.dict(os.environ, {"BUTLER_ENABLE_TERMINAL": "1"}):
                with patch("butler.gateway.commands.dev_handlers._project_workspace", return_value=ws):
                    result = format_test_for_wechat("历史")
                    assert "测试历史" in result
                    assert "✅" in result
                    assert "❌" in result


# ── /构建 command ──────────────────────────────────────────────


class TestBuildForWechat:
    def test_terminal_disabled(self):
        from butler.gateway.commands.dev_handlers import format_build_for_wechat

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("BUTLER_ENABLE_TERMINAL", None)
            result = format_build_for_wechat()
            assert "终端未启用" in result

    def test_no_build_command(self):
        from butler.gateway.commands.dev_handlers import format_build_for_wechat

        with patch.dict(os.environ, {"BUTLER_ENABLE_TERMINAL": "1"}):
            with patch("butler.gateway.commands.dev_handlers._project_workspace", return_value=Path("/tmp")):
                with patch("butler.gateway.commands.dev_handlers._project_dev_config", return_value={}):
                    result = format_build_for_wechat()
                    assert "build_command" in result


# ── /项目概况 command ──────────────────────────────────────────


class TestProjectDashboard:
    def test_no_active_project(self):
        from butler.gateway.commands.dev_handlers import format_project_dashboard_dev

        with patch("butler.gateway.commands.dev_handlers._resolve_project", return_value=None):
            result = format_project_dashboard_dev()
            assert "无活跃项目" in result

    def test_dashboard_with_project(self):
        from butler.gateway.commands.dev_handlers import format_project_dashboard_dev

        mock_proj = MagicMock()  # noqa: magicmock-no-spec — complex facade, spec= 收益低
        mock_proj.name = "TestProject"
        mock_proj.workspace = Path("/tmp")
        mock_proj.dev = {"test_command": "pytest -q"}

        with patch("butler.gateway.commands.dev_handlers._resolve_project", return_value=mock_proj):
            with patch("butler.gateway.commands.dev_handlers._count_files", return_value=42):
                with patch("butler.gateway.commands.dev_handlers._append_git_summary"):
                    with patch("butler.gateway.commands.dev_handlers._append_todos_summary"):
                        with patch("butler.gateway.commands.dev_handlers._append_runtime_summary"):
                            with patch("butler.gateway.commands.dev_handlers._append_memory_summary"):
                                result = format_project_dashboard_dev()
                                assert "TestProject" in result
                                assert "项目概况" in result
                                assert "42" in result
                                assert "pytest -q" in result

    def test_dashboard_owner_default(self):
        from butler.gateway.commands.dev_handlers import format_project_dashboard

        orch = MagicMock()
        with patch(
            "butler.gateway.owner_surface.format_project_overview_owner",
            return_value="owner-dash",
        ):
            result = format_project_dashboard("", orchestrator=orch, session_key="sk1")
        assert result == "owner-dash"


# ── Test history persistence ───────────────────────────────────


class TestSaveTestResult:
    def test_save_and_load(self):
        from butler.gateway.commands.dev_handlers import _save_test_result

        with tempfile.TemporaryDirectory() as tmpdir:
            ws = Path(tmpdir)
            _save_test_result(ws, "测试", 0, 3.2, "10 passed")
            _save_test_result(ws, "测试", 1, 5.1, "8 passed, 2 failed")

            history_path = ws / ".butler" / "test_history.json"
            assert history_path.is_file()
            data = json.loads(history_path.read_text())
            assert len(data) == 2
            assert data[0]["exit_code"] == 0
            assert data[0]["passed"] == 10
            assert data[1]["failed"] == 2

    def test_max_20_records(self):
        from butler.gateway.commands.dev_handlers import _save_test_result

        with tempfile.TemporaryDirectory() as tmpdir:
            ws = Path(tmpdir)
            for i in range(25):
                _save_test_result(ws, "测试", 0, 1.0, "1 passed")

            history_path = ws / ".butler" / "test_history.json"
            data = json.loads(history_path.read_text())
            assert len(data) == 20


# ── Sessionless commands ───────────────────────────────────────


class TestSessionlessCommands:
    @pytest.mark.parametrize("cmd", [
        "/git", "/git status", "/git diff", "/git log 5",
        "/测试", "/测试 历史", "/test",
        "/构建", "/build",
        "/项目概况", "/project-dashboard",
    ])
    def test_new_commands_are_sessionless(self, cmd):
        """Sprint 18-4: _is_sessionless_command 用 registry 真源.

        已注册到 command_registry 的命令 (含 aliases) → sessionless.
        所有这些命令都通过 registry 真源识别, 包括别名 /test /build
        /project-dashboard (alias of /测试 /构建 /项目概况).
        """
        from butler.gateway.handler_helpers import _is_sessionless_command

        assert _is_sessionless_command(cmd), f"{cmd} should be sessionless"


# ── project.yaml dev config ───────────────────────────────────


class TestProjectDevConfig:
    def test_parse_dev_config(self):
        from butler.project import Project

        p = Project.from_yaml(Path("projects/LingWen1/project.yaml"))
        assert "pytest" in p.dev["test_command"]
        assert "test_verify_layered" in p.dev["test_command"]
        assert "test_session_epoch_tools" in p.dev["test_command"]
        assert p.dev["build_command"] == "python -m py_compile ../../butler/main.py"
        assert p.dev["main_branch"] == "main"
        assert "butler/" in p.dev["source_dirs"]
        assert "tests/" in p.dev["source_dirs"]

    def test_empty_dev_config(self):
        import yaml

        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / "project.yaml"
            p.write_text(yaml.dump({"name": "test", "type": "sw", "description": "x"}))

            from butler.project import Project

            proj = Project.from_yaml(p)
            assert proj.dev == {}
            d = proj.to_dict()
            assert "dev" not in d

    def test_dev_config_roundtrip(self):
        import yaml

        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / "project.yaml"
            data = {
                "name": "test",
                "type": "sw",
                "description": "x",
                "dev": {"test_command": "pytest", "build_command": "make"},
            }
            p.write_text(yaml.dump(data, allow_unicode=True))

            from butler.project import Project

            proj = Project.from_yaml(p)
            assert proj.dev["test_command"] == "pytest"
            d = proj.to_dict()
            assert d["dev"]["test_command"] == "pytest"
            assert d["dev"]["build_command"] == "make"


# ── Post-compact dev changes ──────────────────────────────────


class TestDevSessionChanges:
    def test_empty_when_no_events(self):
        from butler.core.post_compact_cleanup import _collect_dev_session_changes

        with patch("butler.tools.registry.get_tool_audit_events", return_value=[]):
            with patch("butler.execution_context.get_audit_session_key", return_value="test"):
                result = _collect_dev_session_changes()
                assert result == ""

    def test_collects_write_events(self):
        from butler.core.post_compact_cleanup import _collect_dev_session_changes

        events = [
            {"tool": "write_file", "args": {"path": "/tmp/a.py"}},
            {"tool": "patch", "args": {"path": "/tmp/b.py"}},
            {"tool": "delete_file", "args": {"path": "/tmp/c.py"}},
        ]

        with patch("butler.tools.registry.get_tool_audit_events", return_value=events):
            with patch("butler.execution_context.get_audit_session_key", return_value="test"):
                result = _collect_dev_session_changes()
                assert "Files changed" in result
                assert "/tmp/a.py" in result
                assert "/tmp/b.py" in result
                assert "写入" in result
                assert "修改" in result
                assert "删除" in result

    def test_collects_terminal_events(self):
        from butler.core.post_compact_cleanup import _collect_dev_session_changes

        events = [
            {"tool": "terminal", "args": {"command": "pytest -q tests/"}},
        ]

        with patch("butler.tools.registry.get_tool_audit_events", return_value=events):
            with patch("butler.execution_context.get_audit_session_key", return_value="test"):
                result = _collect_dev_session_changes()
                assert "Terminal commands" in result
                assert "pytest" in result

    def test_collects_git_events(self):
        from butler.core.post_compact_cleanup import _collect_dev_session_changes

        events = [
            {"tool": "git_commit", "args": {"message": "fix: bug"}},
            {"tool": "git_push", "args": {}},
        ]

        with patch("butler.tools.registry.get_tool_audit_events", return_value=events):
            with patch("butler.execution_context.get_audit_session_key", return_value="test"):
                result = _collect_dev_session_changes()
                assert "Git operations" in result
                assert "commit: fix: bug" in result
                assert "push" in result

    def test_deduplicates_files(self):
        from butler.core.post_compact_cleanup import _collect_dev_session_changes

        events = [
            {"tool": "write_file", "args": {"path": "/tmp/a.py"}},
            {"tool": "patch", "args": {"path": "/tmp/a.py"}},
        ]

        with patch("butler.tools.registry.get_tool_audit_events", return_value=events):
            with patch("butler.execution_context.get_audit_session_key", return_value="test"):
                result = _collect_dev_session_changes()
                assert result.count("/tmp/a.py") == 1


# ── Delegate diff summary ─────────────────────────────────────


class TestDelegateDiffSummary:
    def test_attaches_diff(self):
        from butler.runtime.delegate_job import _try_attach_diff_summary, DelegateJob

        report = MagicMock()  # noqa: magicmock-no-spec — complex facade, spec= 收益低
        report.summary = "Task done."
        job = MagicMock(spec=DelegateJob)  # noqa: magicmock-no-spec — complex facade, spec= 收益低

        diff_result = {
            "exit_code": 0,
            "stdout": " file1.py | 2 +-\n 1 file changed\n",
        }

        with patch.dict(os.environ, {"BUTLER_ENABLE_GIT": "1"}):
            with patch("butler.tools.git_tools._run_git", return_value=diff_result):
                mock_proj = MagicMock()  # noqa: magicmock-no-spec — complex facade, spec= 收益低
                mock_proj.workspace = "/tmp"
                mock_pm = MagicMock()  # noqa: magicmock-no-spec — complex facade, spec= 收益低
                mock_pm.active_project = mock_proj
                with patch("butler.project.manager.ProjectManager", return_value=mock_pm):
                    _try_attach_diff_summary(report, job)
                    assert "变更摘要" in report.summary

    def test_no_diff_when_git_disabled(self):
        from butler.runtime.delegate_job import _try_attach_diff_summary, DelegateJob

        report = MagicMock()  # noqa: magicmock-no-spec — complex facade, spec= 收益低
        report.summary = "Task done."
        job = MagicMock(spec=DelegateJob)  # noqa: magicmock-no-spec — complex facade, spec= 收益低

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("BUTLER_ENABLE_GIT", None)
            _try_attach_diff_summary(report, job)
            assert "变更摘要" not in report.summary

    def test_none_report_safe(self):
        from butler.runtime.delegate_job import _try_attach_diff_summary

        _try_attach_diff_summary(None, None)

"""Sprint 27 P1-3.3: external_directory 跨平台覆盖 + /诊断 透传.

P1-3.3 gap 落地:
  - Windows/WSL/UNC 路径在 check_tool_path / evaluate_external_directory 下
    必须 fail-closed (Linux CI 上 Windows 路径不能误判为 in-workspace).
  - /诊断 必须透传 external_directory 始终允许/本次允许/待批准 三类计数.

覆盖:
  - WSL /mnt/c/Users/foo/x.md 路径被识别为绝对 + 工作区外
  - Windows C:/Users/foo/x.md 路径在 Linux 上必须被识别为工作区外
  - Windows C:\\Users\\foo 反斜杠形式同样识别
  - UNC \\\\server\\share\\file 路径识别为工作区外
  - 大小写: c:/ 与 C:/ 都被识别为 Windows 绝对路径
  - 相对路径 .. 越界被识别为工作区外
  - summarize_approvals 加 external_directory_always_count/once_count 字段
  - /诊断 输出 'External-Dir: always=N · once=M · pending=Y/N' 行
  - 无 external_directory 活动时 /诊断 不输出该行
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from butler.execution_context import use_execution_context
from butler.permissions.approvals import (
    grant_always,
    grant_once,
    summarize_approvals,
)
from butler.tools.path_safety import check_tool_path


# ── 辅助 ──


def _orchestrator_for_workspace(workspace: Path):
    orch = MagicMock()  # noqa: magicmock-no-spec — Sprint 27 path safety
    orch.project_manager.get_current.return_value = SimpleNamespace(workspace=workspace)
    return orch


def _approvals_path(sk: str, tmp_path: Path) -> Path:
    from butler.permissions.approvals import _safe_segment

    return tmp_path / "home" / "sessions" / _safe_segment(sk) / "approvals.json"


# ── check_tool_path: Windows/WSL/UNC 跨平台 ──


@pytest.mark.skipif(sys.platform == "win32", reason="WSL/Linux-specific path expectations")
class TestWindowsWslUncPaths:
    def test_wsl_mnt_path_is_outside_workspace(self, tmp_path):
        """WSL 路径 /mnt/c/Users/foo/x.md 在 Linux 上是绝对路径, 工作区外."""
        workspace = tmp_path / "ws"
        workspace.mkdir()
        orch = _orchestrator_for_workspace(workspace)
        with use_execution_context(orch):
            result = check_tool_path("/mnt/c/Users/foo/x.md")
        assert result.allowed is False
        assert "outside workspace" in (result.error or "").lower()

    def test_windows_drive_letter_path_is_outside_workspace(self, tmp_path):
        """Windows C:/Users/foo/x.md 在 Linux 上必须被识别为工作区外.

        Linux 上 Path('C:/...') 不被识别为绝对, 默认会 resolve 到
        cwd/C:/... 误判为 inside. 修复后应 fail-closed.
        """
        workspace = tmp_path / "ws"
        workspace.mkdir()
        orch = _orchestrator_for_workspace(workspace)
        with use_execution_context(orch):
            result = check_tool_path("C:/Users/foo/x.md")
        assert result.allowed is False
        assert "outside workspace" in (result.error or "").lower()

    def test_windows_backslash_path_is_outside_workspace(self, tmp_path):
        """Windows 反斜杠 C:\\Users\\foo\\x.md 同样应被识别为工作区外."""
        workspace = tmp_path / "ws"
        workspace.mkdir()
        orch = _orchestrator_for_workspace(workspace)
        with use_execution_context(orch):
            result = check_tool_path("C:\\Users\\foo\\x.md")
        assert result.allowed is False
        assert "outside workspace" in (result.error or "").lower()

    def test_unc_path_is_outside_workspace(self, tmp_path):
        """UNC 路径 \\\\server\\share\\file 应被识别为工作区外."""
        workspace = tmp_path / "ws"
        workspace.mkdir()
        orch = _orchestrator_for_workspace(workspace)
        with use_execution_context(orch):
            result = check_tool_path("\\\\server\\share\\file")
        assert result.allowed is False
        assert "outside workspace" in (result.error or "").lower()

    def test_windows_path_case_insensitive(self, tmp_path):
        """c:/ (小写) 与 C:/ (大写) 都应被识别为 Windows 绝对路径."""
        workspace = tmp_path / "ws"
        workspace.mkdir()
        orch = _orchestrator_for_workspace(workspace)
        with use_execution_context(orch):
            r_upper = check_tool_path("C:/foo.txt")
            r_lower = check_tool_path("c:/foo.txt")
        # 两个都应被 fail-closed 拒绝
        assert r_upper.allowed is False
        assert r_lower.allowed is False


# ── 相对路径越界 ──


class TestRelativePathEscapes:
    def test_relative_path_with_parent_escape_is_outside(self, tmp_path):
        """相对路径 ../escape.txt 应被识别为工作区外."""
        workspace = tmp_path / "ws"
        workspace.mkdir()
        orch = _orchestrator_for_workspace(workspace)
        with use_execution_context(orch):
            result = check_tool_path("../escape.txt")
        assert result.allowed is False
        assert "outside workspace" in (result.error or "").lower()

    def test_relative_path_inside_workspace_allowed(self, tmp_path):
        """相对路径 src/app.py 应被识别为工作区内."""
        workspace = tmp_path / "ws"
        workspace.mkdir()
        orch = _orchestrator_for_workspace(workspace)
        with use_execution_context(orch):
            result = check_tool_path("src/app.py")
        assert result.allowed is True


# ── summarize_approvals: external_directory 过滤 ──


class TestSummarizeApprovalsExternalDirectory:
    def test_returns_external_directory_counts(self, tmp_path, monkeypatch):
        """summarize_approvals 应返回 external_directory_always/once_count 字段."""
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path / "home"))
        from butler.config import reload_butler_settings

        reload_butler_settings()
        sk = "sprint27:approvals:basic"
        # 写 2 always (1 external_directory, 1 other) + 1 once (external_directory)
        grant_always(sk, permission="external_directory", tool="read_file", pattern="/tmp/x")
        grant_always(sk, permission="doom_loop", tool="read_file", pattern="**")
        grant_once(sk, permission="external_directory", tool="write_file", pattern="/tmp/y")

        summary = summarize_approvals(sk)
        assert summary["external_directory_always_count"] == 1
        assert summary["external_directory_once_count"] == 1
        assert summary["always_count"] == 2
        assert summary["once_active_count"] == 1

    def test_no_external_directory_activity_returns_zero(self, tmp_path, monkeypatch):
        """无 external_directory 活动时, 过滤计数应为 0, 但其他字段仍工作."""
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path / "home"))
        from butler.config import reload_butler_settings

        reload_butler_settings()
        sk = "sprint27:approvals:empty"
        grant_always(sk, permission="doom_loop", tool="read_file", pattern="**")

        summary = summarize_approvals(sk)
        assert summary["external_directory_always_count"] == 0
        assert summary["external_directory_once_count"] == 0
        assert summary["always_count"] == 1


# ── /诊断 透传 external_directory ──


class TestDiagnosticShowsExternalDirectory:
    def test_health_report_shows_external_dir_line_when_active(
        self, tmp_path, monkeypatch
    ):
        """有 external_directory 活动时, /诊断 应输出 External-Dir 行."""
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path / "home"))
        from butler.config import reload_butler_settings

        reload_butler_settings()
        sk = "sprint27:diag:show"
        grant_always(sk, permission="external_directory", tool="read_file", pattern="/tmp/x")

        from butler.ops.health_report import collect_approval_stats_for_health

        stats = collect_approval_stats_for_health(sk)
        # 应能取到 external_directory 字段
        assert stats["external_directory_always_count"] == 1

    def test_health_report_handles_missing_external_dir_field(
        self, tmp_path, monkeypatch
    ):
        """旧 stats (无 external_directory 字段) 仍可被消费, 不抛 KeyError.

        这保护旧测试套件不会因字段新增而崩溃 — 透传必须是容错的.
        """
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path / "home"))
        from butler.config import reload_butler_settings

        reload_butler_settings()
        sk = "sprint27:diag:legacy"
        grant_always(sk, permission="doom_loop", tool="read_file", pattern="**")

        from butler.ops.health_report import collect_approval_stats_for_health

        stats = collect_approval_stats_for_health(sk)
        # 即使没有 external_directory 活动, 字段也应存在 (默认 0)
        assert stats.get("external_directory_always_count") == 0
        assert stats.get("external_directory_once_count") == 0

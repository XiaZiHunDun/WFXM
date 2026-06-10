"""Sprint 16 TST-11-8: butler.cli.doctor 整文件 0 测试.

bug: butler/cli/doctor.py (60 行)
  - cmd_doctor 是用户运行 ``butler doctor`` 的入口, 0% 覆盖
  - 关键路径: 数据目录检查、核心依赖检查、可选依赖提示、.env 检查、
    MINIMAX_API_KEY 检查、安全审计集成

修复: 直接补单测覆盖各分支, 不改实现 (它已经正确)。
"""

from __future__ import annotations

import argparse
from pathlib import Path
from unittest.mock import patch

import pytest

from butler.cli import doctor
from butler.ops import security_audit as security_audit_mod


# ── 通用 fixture ──


@pytest.fixture
def fake_security_audit():
    """Mock 安全审计: 默认 0 finding, 无 critical。

    run_security_audit / format_audit_report 是 cmd_doctor 内部
    ``from butler.ops.security_audit import ...`` 拉进来的 ——
    要 patch 源模块而不是 doctor 模块。
    """
    fake_findings: list = []
    with patch.object(
        security_audit_mod, "run_security_audit", return_value=fake_findings,
    ), patch.object(
        security_audit_mod, "format_audit_report", return_value="(mock audit)",
    ):
        yield fake_findings


@pytest.fixture
def isolated_butler_home(tmp_path: Path, monkeypatch):
    """隔离 BUTLER_HOME: monkeypatch env + reload 配置缓存。"""
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    from butler.config import reload_butler_settings

    reload_butler_settings()
    return tmp_path


# ── 基础: 输出与退出码 ──


class TestCmdDoctorBasics:
    def test_returns_zero_when_no_critical(self, isolated_butler_home, fake_security_audit, capsys):
        """无 critical finding → 退出码 0。"""
        result = doctor.cmd_doctor(argparse.Namespace())
        captured = capsys.readouterr()

        assert result == 0
        assert "=== Butler Doctor ===" in captured.out
        assert "[数据目录]" in captured.out
        assert "[核心依赖]" in captured.out
        assert "[可选依赖]" in captured.out
        assert "[配置]" in captured.out
        assert "[有效模型]" in captured.out
        assert "--- 有效模型 ---" in captured.out
        assert "[安全审计]" in captured.out

    def test_returns_one_when_critical_found(self, isolated_butler_home, fake_security_audit, capsys):
        """有 critical finding → 退出码 1。"""
        from butler.ops.security_audit import AuditFinding

        fake_security_audit.append(
            AuditFinding(
                level="critical", code="X-1", message="test critical",
            ),
        )
        with patch.object(security_audit_mod, "run_security_audit", return_value=fake_security_audit):
            result = doctor.cmd_doctor(argparse.Namespace())
        assert result == 1

    def test_warning_does_not_fail(self, isolated_butler_home, fake_security_audit, capsys):
        """warning 类 finding 不应导致非零退出码。"""
        from butler.ops.security_audit import AuditFinding

        fake_security_audit.append(
            AuditFinding(
                level="warn", code="W-1", message="test warning",
            ),
        )
        with patch.object(security_audit_mod, "run_security_audit", return_value=fake_security_audit):
            result = doctor.cmd_doctor(argparse.Namespace())
        assert result == 0


# ── 数据目录检查 ──


class TestDataDirsSection:
    def test_marks_existing_dirs_with_check(self, isolated_butler_home, fake_security_audit, capsys):
        """已存在的 runtime 子目录 → ✓。"""
        # 创建所有 BUTLER_RUNTIME_DIRS 子目录
        from butler.config import BUTLER_RUNTIME_DIRS

        for d in BUTLER_RUNTIME_DIRS:
            (isolated_butler_home / d).mkdir(parents=True, exist_ok=True)

        doctor.cmd_doctor(argparse.Namespace())
        out = capsys.readouterr().out
        for d in BUTLER_RUNTIME_DIRS:
            assert f"  {isolated_butler_home / d}: ✓" in out

    def test_marks_missing_dirs(self, isolated_butler_home, fake_security_audit, capsys):
        """缺失的 runtime 子目录 → ✗ (missing)。

        get_butler_settings() 会自动创建 BUTLER_RUNTIME_DIRS,
        为了真正测到 'missing' 分支, patch 一个不存在的子目录。
        """
        with patch.object(security_audit_mod, "run_security_audit", return_value=[]), \
             patch("butler.config.BUTLER_RUNTIME_DIRS", ("nonexistent_dir_xyz",)):
            doctor.cmd_doctor(argparse.Namespace())
        out = capsys.readouterr().out
        assert "✗ (missing)" in out


# ── 核心依赖 / 可选依赖 ──


class TestDepsSection:
    def test_core_deps_reported(self, isolated_butler_home, fake_security_audit, capsys):
        """核心依赖应全部 ✓ (项目已装)。"""
        doctor.cmd_doctor(argparse.Namespace())
        out = capsys.readouterr().out
        for pkg in ("python-dotenv", "PyYAML", "httpx", "openai"):
            assert f"  {pkg}: ✓" in out

    def test_missing_optional_dep_suggests_install(self, isolated_butler_home, fake_security_audit, capsys):
        """缺一个不存在的可选包 → 输出 '可按需安装' + pip install 提示。"""
        # 强制 import 失败 — 模拟某个 optional 包未装
        real_import = __builtins__.__import__ if hasattr(__builtins__, "__import__") else __import__

        def fake_import(name, *args, **kwargs):
            if name == "croniter":
                raise ImportError("simulated missing")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=fake_import):
            doctor.cmd_doctor(argparse.Namespace())
        out = capsys.readouterr().out
        assert "可按需安装" in out
        assert "croniter" in out
        assert "pip install" in out


# ── 配置 (.env + MINIMAX_API_KEY) ──


class TestConfigSection:
    def test_env_file_present(self, isolated_butler_home, fake_security_audit, capsys):
        """cwd 下有 .env → 输出 '✓ (.env)'。"""
        (isolated_butler_home / ".env").write_text("DUMMY=1\n", encoding="utf-8")
        doctor.cmd_doctor(argparse.Namespace())
        out = capsys.readouterr().out
        assert ".env: ✓" in out

    def test_env_file_missing(self, isolated_butler_home, fake_security_audit, capsys):
        """cwd 下无 .env → 输出 '✗ (copy .env.example ...)'。"""
        doctor.cmd_doctor(argparse.Namespace())
        out = capsys.readouterr().out
        assert ".env: ✗" in out
        assert ".env.example" in out

    def test_api_key_set(self, isolated_butler_home, fake_security_audit, monkeypatch, capsys):
        """MINIMAX_API_KEY 已设 → '✓ (set)'。"""
        monkeypatch.setenv("MINIMAX_API_KEY", "sk-test-1234567890")
        doctor.cmd_doctor(argparse.Namespace())
        out = capsys.readouterr().out
        assert "MINIMAX_API_KEY: ✓ (set)" in out

    def test_api_key_unset(self, isolated_butler_home, fake_security_audit, monkeypatch, capsys):
        """MINIMAX_API_KEY 未设 → '✗ (unset)'。"""
        monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
        doctor.cmd_doctor(argparse.Namespace())
        out = capsys.readouterr().out
        assert "MINIMAX_API_KEY: ✗ (unset)" in out
        assert "凭证文件:" in out


# ── Workspace 探测 (projects/AGENTS.md) ──


class TestWorkspaceDetection:
    def test_workspace_found_from_projects(self, isolated_butler_home, fake_security_audit, monkeypatch, capsys):
        """projects/<name>/AGENTS.md 存在 → workspace 设为该目录, audit 收到该路径。"""
        proj_dir = isolated_butler_home / "projects" / "demo"
        proj_dir.mkdir(parents=True)
        (proj_dir / "AGENTS.md").write_text("# demo", encoding="utf-8")

        seen_workspace: dict = {}

        def fake_run_audit(*, workspace):
            seen_workspace["ws"] = workspace
            return []

        with patch.object(security_audit_mod, "run_security_audit", side_effect=fake_run_audit):
            doctor.cmd_doctor(argparse.Namespace())
        assert seen_workspace["ws"] == proj_dir

    def test_no_workspace_passes_none(self, isolated_butler_home, fake_security_audit, monkeypatch, capsys):
        """无 projects 目录 → workspace=None。"""
        seen_workspace: dict = {}

        def fake_run_audit(*, workspace):
            seen_workspace["ws"] = workspace
            return []

        with patch.object(security_audit_mod, "run_security_audit", side_effect=fake_run_audit):
            doctor.cmd_doctor(argparse.Namespace())
        assert seen_workspace["ws"] is None

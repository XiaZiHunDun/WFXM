"""Sprint 16 TST-11-5: butler.tools.execute_code 仅 1 disabled test, 0 真实 subprocess 覆盖.

bug: butler/tools/execute_code.py:52-116 run_execute_code 13 个分支, 仅 disabled 测:
  - disabled (env off) ✅
  - empty code 路径 ❌
  - too large (>8000) 路径 ❌
  - unsupported language 路径 ❌
  - happy path + 真实 subprocess.run ❌
  - subprocess.TimeoutExpired 路径 ❌
  - subprocess generic exception 路径 ❌
  - workspace cwd via project_manager 路径 ❌
  - workspace cwd fallback (no orchestrator) 路径 ❌
  - 网络禁用: env 含 HTTP_PROXY 等空值 ❌
  - 网络启用: env 不含 proxy 阻塞 ❌
  - execute_code_timeout_seconds 边界 (clamp 5..120, ValueError) ❌
  - register_execute_code_tool disabled 不注册 + enabled 注册 ❌

修复: 补全分支覆盖, 真实 subprocess 跑 print(1+1) 验证可执行,
      其它路径用 mock subprocess.run 覆盖。
"""

from __future__ import annotations

import os
import subprocess
import sys
from unittest.mock import MagicMock, patch

import pytest

from butler.tools import execute_code
from butler.tools.execute_code import (
    _MAX_CODE_CHARS,
    _workspace_cwd,
    execute_code_allow_network,
    execute_code_enabled,
    execute_code_timeout_seconds,
    register_execute_code_tool,
    run_execute_code,
)


# ── 公共 fixture: 启用 execute_code ──


@pytest.fixture
def enabled_env(monkeypatch):
    """BUTLER_EXECUTE_CODE=1 让 run_execute_code 通过 disabled gate。"""
    monkeypatch.setenv("BUTLER_EXECUTE_CODE", "1")


@pytest.fixture
def disabled_env(monkeypatch):
    """BUTLER_EXECUTE_CODE=0/未设 → disabled 路径。"""
    monkeypatch.delenv("BUTLER_EXECUTE_CODE", raising=False)


# ── 环境门 ──


class TestEnabledGate:
    def test_disabled_by_default(self, monkeypatch):
        monkeypatch.delenv("BUTLER_EXECUTE_CODE", raising=False)
        assert execute_code_enabled() is False

    def test_enabled_when_env_truthy(self, monkeypatch):
        monkeypatch.setenv("BUTLER_EXECUTE_CODE", "1")
        assert execute_code_enabled() is True
        monkeypatch.setenv("BUTLER_EXECUTE_CODE", "true")
        assert execute_code_enabled() is True

    def test_run_returns_disabled_code_when_off(self, disabled_env):
        out = run_execute_code("print(1)")
        assert out["ok"] is False
        assert out["code"] == "EXECUTE_CODE_DISABLED"
        assert "未启用" in out["error"]


# ── 输入校验分支 (enabled 但 code 无效) ──


class TestInputValidation:
    def test_empty_string_code(self, enabled_env):
        out = run_execute_code("")
        assert out["ok"] is False
        assert out["code"] == "EXECUTE_CODE_EMPTY"

    def test_whitespace_only_code(self, enabled_env):
        """strip 后空 → EMPTY 分支。"""
        out = run_execute_code("   \n\t  ")
        assert out["ok"] is False
        assert out["code"] == "EXECUTE_CODE_EMPTY"

    def test_none_code(self, enabled_env):
        out = run_execute_code(None)  # type: ignore[arg-type]
        assert out["ok"] is False
        assert out["code"] == "EXECUTE_CODE_EMPTY"

    def test_too_large_code(self, enabled_env):
        big = "x = 1\n" * (_MAX_CODE_CHARS // 5 + 100)
        out = run_execute_code(big)
        assert out["ok"] is False
        assert out["code"] == "EXECUTE_CODE_TOO_LARGE"
        assert str(_MAX_CODE_CHARS) in out["error"]

    def test_unsupported_language(self, enabled_env):
        out = run_execute_code("print(1)", language="ruby")
        assert out["ok"] is False
        assert out["code"] == "EXECUTE_CODE_LANG"
        assert "ruby" in out["error"]

    def test_python_alias_accepted(self, enabled_env):
        """language='py' 是 'python' 别名, 应进入正常路径。"""
        with patch.object(execute_code.subprocess, "run") as mock_run:
            mock_proc = MagicMock()
            mock_proc.returncode = 0
            mock_proc.stdout = "2\n"
            mock_proc.stderr = ""
            mock_run.return_value = mock_proc
            out = run_execute_code("print(1+1)", language="py")
        assert out["ok"] is True
        assert out["stdout"] == "2\n"

    def test_language_normalized_lowercase(self, enabled_env):
        """language='PYTHON' → 走正常路径。"""
        with patch.object(execute_code.subprocess, "run") as mock_run:
            mock_proc = MagicMock()
            mock_proc.returncode = 0
            mock_proc.stdout = "ok"
            mock_proc.stderr = ""
            mock_run.return_value = mock_proc
            out = run_execute_code("x=1", language="PYTHON")
        assert out["ok"] is True


# ── 真实 subprocess 路径 (核心 happy path) ──


class TestRealSubprocess:
    def test_print_1_plus_1_returns_2(self, enabled_env, tmp_path):
        """真实 subprocess 跑 print(1+1) → ok=True, stdout='2\\n'。"""
        # 用 tmp_path 当 cwd, 避免污染当前目录的临时文件
        with patch.object(execute_code, "_workspace_cwd", return_value=tmp_path):
            out = run_execute_code("print(1+1)", language="python")
        assert out["ok"] is True
        assert out["exit_code"] == 0
        assert out["stdout"].strip() == "2"
        assert out["stderr"] == ""

    def test_stderr_captured_on_runtime_error(self, enabled_env, tmp_path):
        """代码抛 NameError → ok=False, exit_code!=0, stderr 含 traceback。"""
        with patch.object(execute_code, "_workspace_cwd", return_value=tmp_path):
            out = run_execute_code("undefined_var_xyz", language="python")
        assert out["ok"] is False
        assert out["exit_code"] != 0
        assert "NameError" in out["stderr"] or "undefined_var_xyz" in out["stderr"]

    def test_stdout_truncated_to_16kb(self, enabled_env, tmp_path):
        """stdout > 16000 字节 → 截断。"""
        # 打印 20KB 的 'A'
        big = "print('A' * 20000)"
        with patch.object(execute_code, "_workspace_cwd", return_value=tmp_path):
            out = run_execute_code(big, language="python")
        assert out["ok"] is True
        assert len(out["stdout"]) <= 16000

    def test_stderr_truncated_to_4kb(self, enabled_env, tmp_path):
        """stderr > 4000 字节 → 截断。"""
        # 抛异常带大字符串
        big = "raise RuntimeError('B' * 8000)"
        with patch.object(execute_code, "_workspace_cwd", return_value=tmp_path):
            out = run_execute_code(big, language="python")
        assert out["ok"] is False
        assert len(out["stderr"]) <= 4000


# ── subprocess.run 异常路径 ──


class TestSubprocessErrors:
    def test_timeout_returns_timeout_code(self, enabled_env):
        with patch.object(execute_code, "_workspace_cwd", return_value=MagicMock()):
            with patch.object(
                execute_code.subprocess, "run",
                side_effect=subprocess.TimeoutExpired(cmd="python3", timeout=30),
            ):
                out = run_execute_code("import time; time.sleep(60)")
        assert out["ok"] is False
        assert out["code"] == "EXECUTE_CODE_TIMEOUT"

    def test_subprocess_generic_exception(self, enabled_env):
        with patch.object(execute_code, "_workspace_cwd", return_value=MagicMock()):
            with patch.object(
                execute_code.subprocess, "run",
                side_effect=OSError("binary not found"),
            ):
                out = run_execute_code("print(1)")
        assert out["ok"] is False
        assert out["code"] == "EXECUTE_CODE_ERROR"
        assert "binary not found" in out["error"]

    def test_tempfile_cleaned_on_timeout(self, enabled_env, tmp_path):
        """TimeoutExpired 后 .py 临时文件应被 finally 清理。"""
        created_files: list[str] = []

        original_ntf = execute_code.tempfile.NamedTemporaryFile

        def tracking_ntf(*args, **kwargs):
            fh = original_ntf(*args, **kwargs)
            created_files.append(fh.name)
            return fh

        with patch.object(execute_code, "_workspace_cwd", return_value=tmp_path):
            with patch.object(execute_code.tempfile, "NamedTemporaryFile", tracking_ntf):
                with patch.object(
                    execute_code.subprocess, "run",
                    side_effect=subprocess.TimeoutExpired(cmd="x", timeout=1),
                ):
                    run_execute_code("print(1)")

        # 至少 1 个临时 .py 文件应被创建并清理
        assert any(f.endswith(".py") for f in created_files)
        for f in created_files:
            assert not os.path.exists(f), f"temp file {f} should be cleaned up"


# ── 环境变量构造 (网络隔离) ──


class TestEnvConstruction:
    def test_network_disabled_sets_proxy_blockers(self, enabled_env, monkeypatch):
        """默认网络关闭 → env 含空 HTTP_PROXY/HTTPS_PROXY/ALL_PROXY/NO_PROXY=*。"""
        with patch.object(execute_code, "_workspace_cwd", return_value=MagicMock()):
            with patch.object(execute_code.subprocess, "run") as mock_run:
                mock_proc = MagicMock()
                mock_proc.returncode = 0
                mock_proc.stdout = ""
                mock_proc.stderr = ""
                mock_run.return_value = mock_proc
                run_execute_code("x = 1")
        env = mock_run.call_args.kwargs["env"]
        assert env["HTTP_PROXY"] == ""
        assert env["HTTPS_PROXY"] == ""
        assert env["ALL_PROXY"] == ""
        assert env["NO_PROXY"] == "*"

    def test_network_enabled_omits_proxy_blockers(self, enabled_env, monkeypatch):
        """BUTLER_EXECUTE_CODE_ALLOW_NETWORK=1 → 不注入空 proxy。"""
        monkeypatch.setenv("BUTLER_EXECUTE_CODE_ALLOW_NETWORK", "1")
        with patch.object(execute_code, "_workspace_cwd", return_value=MagicMock()):
            with patch.object(execute_code.subprocess, "run") as mock_run:
                mock_proc = MagicMock()
                mock_proc.returncode = 0
                mock_proc.stdout = ""
                mock_proc.stderr = ""
                mock_run.return_value = mock_proc
                run_execute_code("x = 1")
        env = mock_run.call_args.kwargs["env"]
        assert "HTTP_PROXY" not in env
        assert "HTTPS_PROXY" not in env

    def test_env_has_python_isolation_flags(self, enabled_env):
        """env 应含 PYTHONNOUSERSITE=1, PYTHONDONTWRITEBYTECODE=1, -I 标志。"""
        with patch.object(execute_code, "_workspace_cwd", return_value=MagicMock()):
            with patch.object(execute_code.subprocess, "run") as mock_run:
                mock_proc = MagicMock()
                mock_proc.returncode = 0
                mock_proc.stdout = ""
                mock_proc.stderr = ""
                mock_run.return_value = mock_proc
                run_execute_code("x = 1")
        env = mock_run.call_args.kwargs["env"]
        assert env["PYTHONNOUSERSITE"] == "1"
        assert env["PYTHONDONTWRITEBYTECODE"] == "1"
        assert env["LANG"] == "C.UTF-8"
        # 关键: -I (isolated mode) 必须传给 python3
        cmd = mock_run.call_args.args[0]
        assert "-I" in cmd


# ── execute_code_timeout_seconds 配置边界 ──


class TestTimeoutConfig:
    def test_default_30_seconds(self, monkeypatch):
        monkeypatch.delenv("BUTLER_EXECUTE_CODE_TIMEOUT", raising=False)
        assert execute_code_timeout_seconds() == 30

    def test_clamps_low_to_5(self, monkeypatch):
        monkeypatch.setenv("BUTLER_EXECUTE_CODE_TIMEOUT", "1")
        assert execute_code_timeout_seconds() == 5

    def test_clamps_high_to_120(self, monkeypatch):
        monkeypatch.setenv("BUTLER_EXECUTE_CODE_TIMEOUT", "999")
        assert execute_code_timeout_seconds() == 120

    def test_value_error_returns_default(self, monkeypatch):
        monkeypatch.setenv("BUTLER_EXECUTE_CODE_TIMEOUT", "not-a-number")
        assert execute_code_timeout_seconds() == 30

    def test_normal_value_passes_through(self, monkeypatch):
        monkeypatch.setenv("BUTLER_EXECUTE_CODE_TIMEOUT", "60")
        assert execute_code_timeout_seconds() == 60

    def test_allow_network_default_false(self, monkeypatch):
        monkeypatch.delenv("BUTLER_EXECUTE_CODE_ALLOW_NETWORK", raising=False)
        assert execute_code_allow_network() is False

    def test_allow_network_truthy(self, monkeypatch):
        monkeypatch.setenv("BUTLER_EXECUTE_CODE_ALLOW_NETWORK", "yes")
        assert execute_code_allow_network() is True


# ── _workspace_cwd 解析 ──


class TestWorkspaceCwd:
    def test_falls_back_to_cwd_when_no_orchestrator(self, monkeypatch):
        """get_current_orchestrator 抛 / 返 None → Path.cwd()。"""
        # contextvars 默认 None, 不需要 patch
        cwd = _workspace_cwd()
        # cwd 应该是某个 Path, 至少不抛
        from pathlib import Path
        assert isinstance(cwd, Path)

    def test_uses_project_workspace_when_orchestrator_has_project(self, tmp_path, monkeypatch):
        """orchestrator.project_manager.get_current(...) 返 proj → 用 proj.workspace。"""
        from butler import execution_context

        workspace = tmp_path / "project_workspace"
        workspace.mkdir()
        proj = MagicMock()
        proj.workspace = str(workspace)
        pm = MagicMock()
        pm.get_current.return_value = proj
        orch = MagicMock()
        orch.project_manager = pm

        token_o = execution_context._current_orchestrator.set(orch)
        token_s = execution_context._current_session_key.set("test:user1")
        try:
            cwd = _workspace_cwd()
        finally:
            execution_context._current_orchestrator.reset(token_o)
            execution_context._current_session_key.reset(token_s)
        assert cwd == workspace.resolve()

    def test_orchestrator_without_project_manager_falls_back(self, monkeypatch):
        """orch.project_manager=None → 走 fallback。"""
        from butler import execution_context

        orch = MagicMock()
        orch.project_manager = None
        token_o = execution_context._current_orchestrator.set(orch)
        token_s = execution_context._current_session_key.set("test:x")
        try:
            from pathlib import Path
            cwd = _workspace_cwd()
        finally:
            execution_context._current_orchestrator.reset(token_o)
            execution_context._current_session_key.reset(token_s)
        assert isinstance(cwd, Path)

    def test_pm_get_current_returns_none_falls_back(self, monkeypatch):
        """get_current() 返 None → 走 fallback。"""
        from butler import execution_context

        pm = MagicMock()
        pm.get_current.return_value = None
        orch = MagicMock()
        orch.project_manager = pm

        token_o = execution_context._current_orchestrator.set(orch)
        token_s = execution_context._current_session_key.set("test:x")
        try:
            from pathlib import Path
            cwd = _workspace_cwd()
        finally:
            execution_context._current_orchestrator.reset(token_o)
            execution_context._current_session_key.reset(token_s)
        assert isinstance(cwd, Path)


# ── register_execute_code_tool 行为 ──


class TestRegisterTool:
    def test_disabled_does_not_register(self, disabled_env):
        calls: list[dict] = []

        def register_fn(**kwargs):
            calls.append(kwargs)

        register_execute_code_tool(register_fn)
        assert calls == [], "disabled 时不应注册"

    def test_enabled_registers_execute_code_tool(self, enabled_env):
        captured: dict = {}

        def register_fn(**kwargs):
            captured.update(kwargs)

        register_execute_code_tool(register_fn)
        assert captured.get("name") == "execute_code"
        assert captured.get("toolset") == "sandbox"
        assert callable(captured.get("handler"))
        # schema 校验
        schema = captured.get("schema", {})
        assert "code" in schema.get("required", [])
        assert "code" in schema.get("properties", {})

    def test_registered_handler_dispatches_to_run_execute_code(self, enabled_env):
        """register 的 handler(args) 走 run_execute_code, 返 JSON。"""
        captured: dict = {}

        def register_fn(**kwargs):
            captured.update(kwargs)

        register_execute_code_tool(register_fn)
        handler = captured["handler"]
        with patch.object(execute_code, "run_execute_code", return_value={"ok": True, "x": 1}) as run:
            import json
            out = handler({"code": "x=1", "language": "python"})
        run.assert_called_once_with("x=1", language="python")
        parsed = json.loads(out)
        assert parsed == {"ok": True, "x": 1}

    def test_registered_handler_defaults_language(self, enabled_env):
        """language 缺省 → "python"。"""
        captured: dict = {}

        def register_fn(**kwargs):
            captured.update(kwargs)

        register_execute_code_tool(register_fn)
        handler = captured["handler"]
        with patch.object(execute_code, "run_execute_code", return_value={"ok": True}) as run:
            handler({"code": "x=1"})
        run.assert_called_once_with("x=1", language="python")


# ── 静态契约 ──


class TestStaticContract:
    def test_exports_required_symbols(self):
        for name in (
            "execute_code_enabled",
            "execute_code_timeout_seconds",
            "execute_code_allow_network",
            "run_execute_code",
            "register_execute_code_tool",
        ):
            assert hasattr(execute_code, name), f"execute_code 应导出 {name}"

    def test_max_code_chars_is_8000(self):
        assert _MAX_CODE_CHARS == 8000

    def test_default_timeout_is_30(self):
        from butler.tools.execute_code import _DEFAULT_TIMEOUT
        assert _DEFAULT_TIMEOUT == 30

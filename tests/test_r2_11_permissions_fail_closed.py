"""R2-11 [H] uniform_fail_closed — log+continue 在权限检查中应转为 fail-closed.

`butler/permissions/rules.py:check_project_permission_block` (line 482-504)
两个 log+continue 分支:
1. experiment mode block check 失败 (line 488-489) → log+continue, 等于
   silently 跳过 experiment 守护, 攻击者可借此绕过实验模式写入限制.
2. workflow step permission check 失败 (line 503-504) → log+continue,
   等于 silently 跳过 allowlist 检查, 攻击者借此在受限 step 调用所有工具.

修复: 把这两个分支提为 helper, helper 内部 catch 后:
- log at ERROR (不再是 WARNING)
- log with exc_info=exc (不是 %s interpolation, traceback 不丢)
- 返回非 None 阻断字符串 (fail-CLOSED, 不再 skip)
- 把失败记入模块级 `permission_failures` 缓冲, 供 /诊断 透明

行为保证:
1) experiment mode check 抛异常 → tool 被 BLOCK, 不再 silent skip
2) workflow step resolve 抛异常 → tool 被 BLOCK (无法应用 allowlist = 拒绝)
3) 两处 catch 必须 log at ERROR with exc_info
4) 两处失败必须写入 module-level diagnostics buffer (read via public reader)
5) 正常路径 (no exception) 行为不变
6) 公共 reader 在测试间隔离 (pytest fixture 清空)
"""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import MagicMock  # noqa: F401 — used for orchestrator fixture

import pytest

from butler.permissions import rules as rules_mod
from butler.permissions.rules import check_project_permission_block


@pytest.fixture(autouse=True)
def _reset_permission_failures():
    """Reset module-level diagnostics buffer between tests."""
    rules_mod.reset_permission_failures()
    yield
    rules_mod.reset_permission_failures()


def _make_orchestrator(workspace: Path) -> MagicMock:
    """Build a mock orchestrator with project_manager returning workspace."""

    class _P:
        def __init__(self, ws: Path):
            self.workspace = ws

    class _Pm:
        def __init__(self, ws: Path):
            self._ws = ws

        def get_current(self, session_key: str = ""):
            return _P(self._ws)

    orch = MagicMock()  # noqa: magicmock-no-spec — permission check fixture
    orch.project_manager = _Pm(workspace)
    return orch


def _bind_orchestrator(monkeypatch, workspace: Path) -> None:
    """Bind a mock orchestrator into butler.execution_context."""
    orch = _make_orchestrator(workspace)
    monkeypatch.setattr(
        "butler.execution_context.get_current_orchestrator",
        lambda: orch,
    )
    monkeypatch.setattr(
        "butler.execution_context.get_current_session_key",
        lambda: "test-session",
    )


# -----------------------------------------------------------------------
# Test 1: experiment mode check failure → BLOCK (fail-closed)
# -----------------------------------------------------------------------


@pytest.mark.unit
class TestExperimentModeFailClosed:
    """`check_experiment_mode_block` 抛异常时, tool 必须被 block."""

    def test_experiment_check_exception_blocks_tool(
        self, tmp_path: Path, monkeypatch, caplog
    ):
        """模拟 experiment 检查函数抛 RuntimeError, tool 应当被拒绝."""
        _bind_orchestrator(monkeypatch, tmp_path)
        monkeypatch.setattr(
            "butler.experiments.mode.check_experiment_mode_block",
            MagicMock(  # noqa: magicmock-no-spec — experiment mock
                side_effect=RuntimeError("simulated experiment detector failure"),
            ),
        )

        with caplog.at_level(logging.ERROR, logger="butler.permissions.rules"):
            result = check_project_permission_block("write_file", {"path": "a.txt"})

        assert result is not None, (
            "experiment mode check 异常时, tool 必须被 block (fail-closed); "
            f"实际 result={result!r}, 这是 fail-OPEN 行为"
        )
        assert "experiment" in result.lower() or "unavailable" in result.lower(), (
            f"denial 理由应说明 experiment mode 不可用, 实际: {result!r}"
        )

    def test_experiment_check_exception_logs_error_with_exc_info(
        self, tmp_path: Path, monkeypatch, caplog
    ):
        """异常必须 log at ERROR with exc_info (保留 traceback, 不只 %s)."""
        _bind_orchestrator(monkeypatch, tmp_path)
        monkeypatch.setattr(
            "butler.experiments.mode.check_experiment_mode_block",
            MagicMock(  # noqa: magicmock-no-spec — experiment mock
                side_effect=RuntimeError("simulated"),
            ),
        )

        with caplog.at_level(logging.DEBUG, logger="butler.permissions.rules"):
            check_project_permission_block("write_file", {"path": "a.txt"})

        error_records = [
            r for r in caplog.records if r.levelno >= logging.ERROR
        ]
        assert error_records, (
            "experiment check 失败必须 log at ERROR, "
            f"实际 records: {[(r.levelname, r.message) for r in caplog.records]}"
        )
        # at least one must have exc_info
        assert any(r.exc_info is not None for r in error_records), (
            "experiment check 失败的 ERROR log 必须含 exc_info (traceback), "
            "不能用 %s interpolation"
        )

    def test_experiment_check_failure_recorded_in_diagnostics(
        self, tmp_path: Path, monkeypatch
    ):
        """失败必须写入模块级 diagnostics buffer, 供 /诊断 透明."""
        _bind_orchestrator(monkeypatch, tmp_path)
        monkeypatch.setattr(
            "butler.experiments.mode.check_experiment_mode_block",
            MagicMock(  # noqa: magicmock-no-spec — experiment mock
                side_effect=RuntimeError("simulated"),
            ),
        )

        assert rules_mod.recent_permission_failures() == []
        check_project_permission_block("write_file", {"path": "a.txt"})
        failures = rules_mod.recent_permission_failures()
        assert len(failures) == 1, (
            f"experiment check 失败应被记入 diagnostics, 实际 {failures!r}"
        )
        assert failures[0]["check"] == "experiment_mode_block"
        assert "RuntimeError" in failures[0]["type"]
        assert "simulated" in failures[0]["error"]


# -----------------------------------------------------------------------
# Test 2: workflow step resolution failure → BLOCK (fail-closed)
# -----------------------------------------------------------------------


@pytest.mark.unit
class TestWorkflowStepFailClosed:
    """`get_current_workflow_step` 抛异常时, tool 必须被 block."""

    def test_workflow_step_resolution_exception_blocks_tool(
        self, tmp_path: Path, monkeypatch, caplog
    ):
        """模拟 step resolver 抛 RuntimeError, tool 应当被拒绝
        (无法确定 step → 无法应用 allowlist → 拒绝)."""
        _bind_orchestrator(monkeypatch, tmp_path)
        monkeypatch.setattr(
            "butler.execution_context.get_current_workflow_step",
            MagicMock(  # noqa: magicmock-no-spec — workflow step mock
                side_effect=RuntimeError("simulated step resolver failure"),
            ),
        )

        with caplog.at_level(logging.ERROR, logger="butler.permissions.rules"):
            result = check_project_permission_block("read_file", {"path": "a.txt"})

        assert result is not None, (
            "workflow step resolve 异常时, tool 必须被 block "
            "(无法应用 allowlist = 拒绝); 实际 result=None (fail-OPEN)"
        )
        assert (
            "workflow" in result.lower() or "step" in result.lower()
            or "allowlist" in result.lower()
        ), (
            f"denial 理由应说明 workflow step 不可用, 实际: {result!r}"
        )

    def test_workflow_step_resolution_logs_error_with_exc_info(
        self, tmp_path: Path, monkeypatch, caplog
    ):
        """异常必须 log at ERROR with exc_info."""
        _bind_orchestrator(monkeypatch, tmp_path)
        monkeypatch.setattr(
            "butler.execution_context.get_current_workflow_step",
            MagicMock(  # noqa: magicmock-no-spec — workflow step mock
                side_effect=RuntimeError("simulated"),
            ),
        )

        with caplog.at_level(logging.DEBUG, logger="butler.permissions.rules"):
            check_project_permission_block("read_file", {"path": "a.txt"})

        error_records = [
            r for r in caplog.records if r.levelno >= logging.ERROR
        ]
        assert error_records, (
            "workflow step resolve 失败必须 log at ERROR"
        )
        assert any(r.exc_info is not None for r in error_records), (
            "ERROR log 必须含 exc_info (traceback)"
        )

    def test_workflow_step_failure_recorded_in_diagnostics(
        self, tmp_path: Path, monkeypatch
    ):
        """失败必须写入 module-level diagnostics buffer."""
        _bind_orchestrator(monkeypatch, tmp_path)
        monkeypatch.setattr(
            "butler.execution_context.get_current_workflow_step",
            MagicMock(  # noqa: magicmock-no-spec — workflow step mock
                side_effect=RuntimeError("simulated"),
            ),
        )

        check_project_permission_block("read_file", {"path": "a.txt"})
        failures = rules_mod.recent_permission_failures()
        assert len(failures) == 1
        assert failures[0]["check"] == "workflow_step_resolve"


# -----------------------------------------------------------------------
# Test 3: normal path is unchanged
# -----------------------------------------------------------------------


@pytest.mark.unit
class TestNormalPathUnchanged:
    """无异常时, 行为不变."""

    def test_no_experiment_no_workflow_step_allows(
        self, tmp_path: Path, monkeypatch
    ):
        """无 experiment mode, 无 workflow step → tool 被允许 (返回 None)."""
        _bind_orchestrator(monkeypatch, tmp_path)
        monkeypatch.setattr(
            "butler.experiments.mode.check_experiment_mode_block",
            lambda *a, **k: None,  # no block
        )
        # default get_current_workflow_step returns ""
        result = check_project_permission_block("read_file", {"path": "a.txt"})
        assert result is None, (
            f"无 block 信号时应返回 None, 实际: {result!r}"
        )
        assert rules_mod.recent_permission_failures() == []

    def test_no_permission_failures_buffered_on_success(
        self, tmp_path: Path, monkeypatch
    ):
        """正常路径不应往 diagnostics buffer 写东西."""
        _bind_orchestrator(monkeypatch, tmp_path)
        monkeypatch.setattr(
            "butler.experiments.mode.check_experiment_mode_block",
            lambda *a, **k: None,
        )
        for _ in range(5):
            check_project_permission_block("read_file", {"path": "a.txt"})
        assert rules_mod.recent_permission_failures() == []


# -----------------------------------------------------------------------
# Test 4: public reader exists & is bounded
# -----------------------------------------------------------------------


@pytest.mark.unit
class TestPublicReader:
    """recent_permission_failures 公共 reader 必须存在并有界."""

    def test_reader_returns_empty_list_initially(self):
        assert isinstance(rules_mod.recent_permission_failures(), list)
        assert rules_mod.recent_permission_failures() == []

    def test_reset_clears_buffer(self, tmp_path: Path, monkeypatch):
        """reset_permission_failures 公开接口必须清空 buffer."""
        _bind_orchestrator(monkeypatch, tmp_path)
        monkeypatch.setattr(
            "butler.experiments.mode.check_experiment_mode_block",
            MagicMock(  # noqa: magicmock-no-spec — experiment mock
                side_effect=RuntimeError("simulated"),
            ),
        )
        check_project_permission_block("read_file", {"path": "a.txt"})
        assert rules_mod.recent_permission_failures()
        rules_mod.reset_permission_failures()
        assert rules_mod.recent_permission_failures() == []

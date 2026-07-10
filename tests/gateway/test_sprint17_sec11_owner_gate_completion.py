"""Sprint 17 SEC-11 owner gate completion: 6 registry handlers + 3 opt-out 标注.

Sprint 11 审计 SEC-11-1/2/4/5/6/7 (6 项 owner-gate) 修复了底层函数层 (handle_*_command)
的 owner 守门, 但 Sprint 16 TST-10-5 迁移 batch 1-5 注册的 registry handler wrapper
(_cmd_sessions / _cmd_outcome / _cmd_health / _cmd_project_list / _cmd_butler_status /
_cmd_runtime_jobs_list) 没有重复加 wrapper-level gate. 静态扫描器
``test_sprint12_owner_gate_scan`` 检出 9 个 gap, 其中 6 个需新增 owner gate, 3 个
(``_cmd_memory_graph`` / ``_cmd_memory_pending_list`` / ``_cmd_memory_reject``) 是
read-only 路径, 显式 opt-out (per ``tests/test_sprint11_sec2_memory_approve_owner.py::
test_unrelated_command_not_blocked_by_owner_gate`` 既有契约).

测试覆盖:
- 6 个 handler: 非 Owner → owner_required_message(); Owner → 调到底层 (mock 验证)
- 3 个 memory handler: opt-out 标记存在 (静态契约)
- owner-gate-scan: 9 → 0 gaps (隐含在 test_sprint12_owner_gate_scan)
"""

from __future__ import annotations

import inspect
import re
from unittest.mock import patch

import pytest

from butler.gateway.command_registry import CommandContext
from butler.gateway.commands import (
    info_commands,
    memory_commands,
    project_commands,
    runtime_commands,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ctx(**overrides):
    """Build a minimal CommandContext for handler tests.

    ``overrides`` keys map to CommandContext fields; ``cmd``/``arg`` default
    to empty, ``external_id`` to "u", ``platform`` to "wechat".
    """
    platform = overrides.get("platform", "wechat")
    external_id = overrides.get("external_id", "u")
    defaults = dict(
        cmd=overrides.get("cmd", ""),
        arg=overrides.get("arg", ""),
        session_key=f"{platform}:{external_id}:proj",
        platform=platform,
        external_id=external_id,
        orchestrator=overrides.get("orchestrator", None),
        session_registry=overrides.get("session_registry", None),
    )
    return CommandContext(**defaults)


# ---------------------------------------------------------------------------
# TestInfoHandlerGates — info_commands.py: _cmd_sessions / _cmd_outcome / _cmd_health
# ---------------------------------------------------------------------------


class TestInfoHandlerGates:
    """Sprint 17 SEC-11-5/6/7: 3 个从 inline 迁移过来的 info handler 加 owner gate.

    已存在的 _require_owner(ctx) helper 在 info_commands.py:11-17, 直接复用.
    """

    @pytest.mark.unit
    def test_sessions_blocked_for_non_owner(self):
        from butler.gateway.owner_gate import owner_required_message

        with patch(
            "butler.gateway.owner_gate.is_gateway_owner",
            return_value=False,
        ):
            out = info_commands._cmd_sessions(_ctx(cmd="/会话", external_id="non_owner"))
        assert out == owner_required_message(), (
            f"非 Owner /会话 应被拒，实际 {out!r}"
        )

    @pytest.mark.unit
    def test_outcome_blocked_for_non_owner(self):
        from butler.gateway.owner_gate import owner_required_message

        with patch(
            "butler.gateway.owner_gate.is_gateway_owner",
            return_value=False,
        ):
            out = info_commands._cmd_outcome(
                _ctx(cmd="/评价", arg="list", external_id="non_owner")
            )
        assert out == owner_required_message(), (
            f"非 Owner /评价 应被拒，实际 {out!r}"
        )

    @pytest.mark.unit
    def test_health_blocked_for_non_owner(self):
        from butler.gateway.owner_gate import owner_required_message

        with patch(
            "butler.gateway.owner_gate.is_gateway_owner",
            return_value=False,
        ):
            out = info_commands._cmd_health(_ctx(cmd="/诊断", external_id="non_owner"))
        assert out == owner_required_message(), (
            f"非 Owner /诊断 应被拒，实际 {out!r}"
        )

    @pytest.mark.unit
    def test_owner_passes_through_sessions(self):
        """Owner 调 /会话 应能走到 sessions_commands.handle_sessions_command."""
        with patch(
            "butler.gateway.owner_gate.is_gateway_owner",
            return_value=True,
        ), patch(
            "butler.gateway.commands.sessions_handlers.handle_sessions_command",
            return_value="sessions list",
        ) as mock_handle:
            out = info_commands._cmd_sessions(
                _ctx(cmd="/会话", external_id="owner_id")
            )
        assert mock_handle.called, "Owner 应能调到 handle_sessions_command"
        assert out == "sessions list", f"Owner 应拿到 sessions list，实际 {out!r}"

    @pytest.mark.unit
    def test_owner_passes_through_outcome(self):
        with patch(
            "butler.gateway.owner_gate.is_gateway_owner",
            return_value=True,
        ), patch(
            "butler.gateway.commands.outcome_handlers.handle_outcome_command",
            return_value="outcome list",
        ) as mock_handle:
            out = info_commands._cmd_outcome(
                _ctx(cmd="/评价", arg="list", external_id="owner_id")
            )
        assert mock_handle.called, "Owner 应能调到 handle_outcome_command"
        assert out == "outcome list", f"Owner 应拿到 outcome list，实际 {out!r}"


# ---------------------------------------------------------------------------
# TestProjectHandlerGates — project_commands.py: _cmd_project_list / _cmd_butler_status
# ---------------------------------------------------------------------------


class TestProjectHandlerGates:
    """Sprint 17 SEC-11 NEW GAP: /项目 /状态 加 owner gate.

    Audit doc 原始 SEC-11-1..7 未列 (migration batch 5 引入), 静态扫描发现
    project list 含描述 + butler status 含 provider/role 均为 owner 私人数据.
    """

    @pytest.mark.unit
    def test_project_list_blocked_for_non_owner(self):
        from butler.gateway.owner_gate import owner_required_message

        with patch(
            "butler.gateway.owner_gate.is_gateway_owner",
            return_value=False,
        ):
            out = project_commands._cmd_project_list(
                _ctx(cmd="/项目", external_id="non_owner")
            )
        assert out == owner_required_message(), (
            f"非 Owner /项目 应被拒，实际 {out!r}"
        )

    @pytest.mark.unit
    def test_butler_status_blocked_for_non_owner(self):
        from butler.gateway.owner_gate import owner_required_message

        with patch(
            "butler.gateway.owner_gate.is_gateway_owner",
            return_value=False,
        ):
            out = project_commands._cmd_butler_status(
                _ctx(cmd="/状态", external_id="non_owner")
            )
        assert out == owner_required_message(), (
            f"非 Owner /状态 应被拒，实际 {out!r}"
        )

    @pytest.mark.unit
    def test_owner_passes_through_project_list(self):
        """Owner 调 /项目 应能拿到项目列表 (mock project_manager)."""
        fake_orch = type("O", (), {})()
        fake_pm = type("PM", (), {
            "list_projects": staticmethod(lambda: []),
            "resolve_active_project_name": staticmethod(lambda **kw: None),
        })()
        fake_orch.project_manager = fake_pm

        with patch(
            "butler.gateway.owner_gate.is_gateway_owner",
            return_value=True,
        ):
            out = project_commands._cmd_project_list(
                _ctx(cmd="/项目", external_id="owner_id", orchestrator=fake_orch)
            )
        assert "暂无项目" in out, f"Owner 应拿到项目列表（空时返 '暂无项目'），实际 {out!r}"

    @pytest.mark.unit
    def test_owner_passes_through_butler_status(self):
        """Owner 调 /状态 应能拿到 butler 状态 (mock orchestrator)."""
        fake_orch = type("O", (), {})()
        fake_orch._settings = type("S", (), {
            "butler_name": "Butler",
            "default_provider": "anthropic",
        })()
        fake_pm = type("PM", (), {
            "get_current": staticmethod(lambda **kw: None),
            "resolve_active_project_name": staticmethod(lambda **kw: "(无)"),
        })()
        fake_orch.project_manager = fake_pm

        with patch(
            "butler.gateway.owner_gate.is_gateway_owner",
            return_value=True,
        ):
            out = project_commands._cmd_butler_status(
                _ctx(cmd="/状态", external_id="owner_id", orchestrator=fake_orch)
            )
        assert "Butler 状态" in out, f"Owner 应拿到 Butler 状态，实际 {out!r}"


# ---------------------------------------------------------------------------
# TestRuntimeHandlerGates — runtime_commands.py: _cmd_runtime_jobs_list
# ---------------------------------------------------------------------------


class TestRuntimeHandlerGates:
    """Sprint 17 SEC-11-1 扩展: /定时 (read-only jobs list) 也加 owner gate.

    Audit SEC-11-1 只覆盖 /运行 /批准运行 (改盘). /定时 仅列出 jobs, 但 job
    名 (e.g. ``publish-preflight``) 透露工作流结构, 仍属 owner 数据.
    """

    @pytest.mark.unit
    def test_runtime_jobs_list_blocked_for_non_owner(self):
        from butler.gateway.owner_gate import owner_required_message

        with patch(
            "butler.gateway.commands.runtime_commands.is_gateway_owner",
            return_value=False,
        ):
            out = runtime_commands._cmd_runtime_jobs_list(
                _ctx(cmd="/定时", external_id="non_owner")
            )
        assert out == owner_required_message(), (
            f"非 Owner /定时 应被拒，实际 {out!r}"
        )

    @pytest.mark.unit
    def test_owner_passes_through_runtime_jobs_list(self):
        with patch(
            "butler.gateway.commands.runtime_commands.is_gateway_owner",
            return_value=True,
        ), patch(
            "butler.gateway.commands.runtime_handlers.handle_runtime_command",
            return_value="jobs list",
        ) as mock_handle:
            out = runtime_commands._cmd_runtime_jobs_list(
                _ctx(cmd="/定时", external_id="owner_id")
            )
        assert mock_handle.called, "Owner 应能调到 handle_runtime_command"
        assert out == "jobs list", f"Owner 应拿到 jobs list，实际 {out!r}"


# ---------------------------------------------------------------------------
# TestMemoryHandlerOptOut — 3 个 read-only memory handler 标 owner-gate-opt-out
# ---------------------------------------------------------------------------


_OPT_OUT_MARKER = re.compile(r"owner-gate-opt-out\s*:")


def _first_docstring_lines(source: str, name: str) -> str:
    """Extract the leading docstring of function ``name`` from ``source``.

    Returns empty string if no docstring present.
    """
    m = re.search(rf"def {name}\b.*?\"\"\"(.*?)\"\"\"", source, re.DOTALL)
    if m is None:
        return ""
    return m.group(1)


class TestMemoryHandlerOptOut:
    """Sprint 17 SEC-11-2 read-only 子命令 opt-out 静态契约.

    ``test_sprint11_sec2_memory_approve_owner.py::test_unrelated_command_not_blocked_by_owner_gate``
    既有契约明确: /拒绝记忆 /记忆待审 /记忆图谱 是 read-only 路径, 不强制 owner gate.

    静态扫描器需要 opt-out 标记才能识别豁免. 本测试验证 3 个 handler 都有标记.
    """

    @pytest.mark.unit
    def test_cmd_memory_graph_has_opt_out_marker(self):
        src = inspect.getsource(memory_commands._cmd_memory_graph)
        doc = _first_docstring_lines(src, "_cmd_memory_graph")
        assert _OPT_OUT_MARKER.search(doc), (
            "_cmd_memory_graph 需 owner-gate-opt-out: 标记 (read-only 三元组, "
            "per test_sprint11_sec2 既有契约), 实际 docstring:"
            f"\n{doc!r}"
        )

    @pytest.mark.unit
    def test_cmd_memory_pending_list_has_opt_out_marker(self):
        src = inspect.getsource(memory_commands._cmd_memory_pending_list)
        doc = _first_docstring_lines(src, "_cmd_memory_pending_list")
        assert _OPT_OUT_MARKER.search(doc), (
            "_cmd_memory_pending_list 需 owner-gate-opt-out: 标记 (read-only 待审列表), "
            f"实际 docstring:\n{doc!r}"
        )

    @pytest.mark.unit
    def test_cmd_memory_reject_has_opt_out_marker(self):
        src = inspect.getsource(memory_commands._cmd_memory_reject)
        doc = _first_docstring_lines(src, "_cmd_memory_reject")
        assert _OPT_OUT_MARKER.search(doc), (
            "_cmd_memory_reject 需 owner-gate-opt-out: 标记 (拒绝不入正典, 不污染 "
            f"MEMORY.md), 实际 docstring:\n{doc!r}"
        )

    @pytest.mark.unit
    def test_cmd_memory_graph_actually_skips_gate(self):
        """非 Owner 调 /记忆图谱 应能正常返三元组 (不强制 owner gate)."""
        from unittest.mock import patch

        # 注意: _cmd_memory_graph 是 registry handler, 它的 is_gateway_owner
        # 不在它本身调, 也不通过 helper 调 — 验证 _cmd_memory_graph 真的
        # 不调 is_gateway_owner/_require_owner (静态契约).
        src = inspect.getsource(memory_commands._cmd_memory_graph)
        assert "is_gateway_owner" not in src, (
            "_cmd_memory_graph 不应调 is_gateway_owner (read-only, 应 opt-out)"
        )
        assert "_require_owner" not in src, (
            "_cmd_memory_graph 不应调 _require_owner (read-only, 应 opt-out)"
        )
        # 运行时验证: 非 Owner 调 /记忆图谱 应能正常返 format 结果 (不被拒)
        with patch(
            "butler.gateway.commands.memory_handlers.format_memory_triplet_graph",
            return_value="graph ok",
        ) as mock_fmt:
            out = memory_commands._cmd_memory_graph(
                _ctx(cmd="/记忆图谱", external_id="non_owner")
            )
        assert mock_fmt.called, "non-owner /记忆图谱 应能调到 format_memory_triplet_graph"
        assert out == "graph ok", f"non-owner 应拿到 graph result, 实际 {out!r}"


# ---------------------------------------------------------------------------
# TestScanNoLongerFlagsNewHandlers — 隐含验证: 加完 gate + opt-out 后
# test_sprint12_owner_gate_scan 报 0 gaps. 集成在 sprint12 test, 这里只断言
# 6 个目标 handler 都不再触发 ast 标记.
# ---------------------------------------------------------------------------


class TestHandlerNotFlaggedByScan:
    """直接对 6 个目标 handler 调用 scan_owner_gate_gaps() 验证不被检出.

    测试设计: scan 从 butler/gateway 根扫, 6 个目标 handler 都是 _cmd_* 前缀,
    触发 scan 的 _is_handler. 修复后要么有 gate (6 个新增) 要么有 opt-out
    标记 (3 个 memory), 都不应被列入 gaps.
    """

    @pytest.fixture
    def scan_gap_names(self):
        from tests.test_sprint12_owner_gate_scan import scan_owner_gate_gaps

        gaps = scan_owner_gate_gaps()
        return {gap[1] for gap in gaps}

    @pytest.mark.unit
    def test_sessions_not_flagged(self, scan_gap_names):
        assert "_cmd_sessions" not in scan_gap_names, (
            "_cmd_sessions 应被 owner gate 豁免 (gate 已加)"
        )

    @pytest.mark.unit
    def test_outcome_not_flagged(self, scan_gap_names):
        assert "_cmd_outcome" not in scan_gap_names

    @pytest.mark.unit
    def test_health_not_flagged(self, scan_gap_names):
        assert "_cmd_health" not in scan_gap_names

    @pytest.mark.unit
    def test_project_list_not_flagged(self, scan_gap_names):
        assert "_cmd_project_list" not in scan_gap_names

    @pytest.mark.unit
    def test_butler_status_not_flagged(self, scan_gap_names):
        assert "_cmd_butler_status" not in scan_gap_names

    @pytest.mark.unit
    def test_runtime_jobs_list_not_flagged(self, scan_gap_names):
        assert "_cmd_runtime_jobs_list" not in scan_gap_names

    @pytest.mark.unit
    def test_memory_graph_not_flagged(self, scan_gap_names):
        assert "_cmd_memory_graph" not in scan_gap_names

    @pytest.mark.unit
    def test_memory_pending_list_not_flagged(self, scan_gap_names):
        assert "_cmd_memory_pending_list" not in scan_gap_names

    @pytest.mark.unit
    def test_memory_reject_not_flagged(self, scan_gap_names):
        assert "_cmd_memory_reject" not in scan_gap_names

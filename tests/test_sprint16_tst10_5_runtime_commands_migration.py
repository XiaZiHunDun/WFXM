"""Sprint 16 TST-10-5 第三批: butler.gateway.commands.runtime_commands 迁移测试.

迁移 3 个 runtime 命令:
  - /定时 (/runtime, /定时任务)            → _cmd_runtime_jobs_list
  - /批准运行 (/approve-run, /批准任务)     → _cmd_runtime_approve_run (含 owner gate)
  - /运行 (/run-job, /运行任务)             → _cmd_runtime_run (含 owner gate)

覆盖: 静态契约 + dispatch + 委派 + owner gate + 别名 + 集合缩小
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from butler.gateway.command_registry import (
    CommandContext,
    CommandDef,
    all_commands,
    dispatch,
    lookup,
)
from butler.gateway.commands import runtime_commands as rt_cmds


@pytest.fixture
def ensure_registered():
    import butler.gateway.commands  # noqa: F401
    return None


# ── 静态契约 ──


class TestStaticContract:
    def test_module_exports_3_handlers(self):
        for name in (
            "_cmd_runtime_jobs_list",
            "_cmd_runtime_approve_run",
            "_cmd_runtime_run",
        ):
            assert hasattr(rt_cmds, name), f"runtime_commands 缺 {name}"

    def test_module_defines_3_command_defs(self):
        for cmd in rt_cmds._RUNTIME_COMMANDS:
            assert isinstance(cmd, CommandDef)
            assert cmd.handler is not None

    def test_handler_attribute_set_in_registry(self, ensure_registered):
        for name in ("/定时", "/批准运行", "/运行"):
            cmd = lookup(name)
            assert cmd is not None, f"registry 缺 {name}"
            assert cmd.handler is not None, f"{name} 缺 handler"

    def test_register_runtime_commands_is_idempotent(self):
        before = len(all_commands())
        rt_cmds.register_runtime_commands()
        after = len(all_commands())
        assert before == after

    def test_commands_init_imports_runtime_commands(self):
        from butler.gateway import commands as cmds_pkg
        assert "runtime_commands" in cmds_pkg.__all__
        assert hasattr(cmds_pkg, "runtime_commands")


# ── dispatch + 别名 ──


class TestDispatch:
    @pytest.mark.parametrize(
        "alias,canonical",
        [
            ("/runtime", "/定时"),
            ("/定时任务", "/定时"),
            ("/approve-run", "/批准运行"),
            ("/批准任务", "/批准运行"),
            ("/run-job", "/运行"),
            ("/运行任务", "/运行"),
        ],
    )
    def test_aliases_resolve_to_canonical_handler(self, alias, canonical, ensure_registered):
        cmd = lookup(alias)
        assert cmd is not None
        assert cmd.name == canonical
        assert cmd.handler is not None

    def test_dispatch_returns_handled_true_for_each(self, ensure_registered):
        for name in ("/定时", "/批准运行", "/运行"):
            ctx = CommandContext(
                cmd=name,
                arg="",
                session_key="t:s",
                platform="t",
                external_id="s",
                orchestrator=MagicMock(),  # noqa: magicmock-no-spec — runtime command facade (orch / session_registry)
                session_registry=MagicMock(),  # noqa: magicmock-no-spec — runtime command facade (orch / session_registry)
            )
            with patch.object(rt_cmds, "_cmd_runtime_approve_run", return_value=None) as a, \
                 patch.object(rt_cmds, "_cmd_runtime_run", return_value=None) as r, \
                 patch.object(rt_cmds, "_cmd_runtime_jobs_list", return_value=None):
                handled, _ = dispatch(ctx)
            assert handled is True, f"{name} 仍走 inline"


# ── 行为委派 ──


class TestDelegation:
    def test_jobs_list_passes_canonical_cmd(self, ensure_registered):
        """/定时 handler 强制 cmd='/定时' 委派到 handle_runtime_command。"""
        from butler.gateway.runtime_commands import handle_runtime_command

        orch = MagicMock()  # noqa: magicmock-no-spec — runtime command facade (orch / session_registry)
        ctx = CommandContext(
            cmd="/runtime",  # alias
            arg="",
            session_key="t:s",
            platform="wechat",
            external_id="alice",
            orchestrator=orch,
            session_registry=MagicMock(),  # noqa: magicmock-no-spec — runtime command facade (orch / session_registry)
        )
        with patch.object(rt_cmds, "is_gateway_owner", return_value=True), patch(
            "butler.gateway.runtime_commands.handle_runtime_command",
            return_value="jobs-text",
        ) as h:
            result = rt_cmds._cmd_runtime_jobs_list(ctx)
        assert result == "jobs-text"
        args, _ = h.call_args
        assert args[1] == "/定时", f"应强制 canonical cmd, 实际 {args[1]!r}"

    def test_approve_run_passes_canonical_cmd(self, ensure_registered):
        from butler.gateway.runtime_commands import handle_runtime_command

        orch = MagicMock()  # noqa: magicmock-no-spec — runtime command facade (orch / session_registry)
        ctx = CommandContext(
            cmd="/approve-run",
            arg="job-1",
            session_key="t:s",
            platform="wechat",
            external_id="owner1",
            orchestrator=orch,
            session_registry=MagicMock(),  # noqa: magicmock-no-spec — runtime command facade (orch / session_registry)
        )
        with patch.object(rt_cmds, "is_gateway_owner", return_value=True), patch(
            "butler.gateway.runtime_commands.handle_runtime_command",
            return_value="approved",
        ) as h:
            result = rt_cmds._cmd_runtime_approve_run(ctx)
        assert result == "approved"
        args, _ = h.call_args
        assert args[1] == "/批准运行"
        assert args[2] == "job-1"

    def test_run_passes_canonical_cmd(self, ensure_registered):
        from butler.gateway.runtime_commands import handle_runtime_command

        orch = MagicMock()  # noqa: magicmock-no-spec — runtime command facade (orch / session_registry)
        ctx = CommandContext(
            cmd="/run-job",
            arg="job-2",
            session_key="t:s",
            platform="wechat",
            external_id="owner1",
            orchestrator=orch,
            session_registry=MagicMock(),  # noqa: magicmock-no-spec — runtime command facade (orch / session_registry)
        )
        with patch.object(rt_cmds, "is_gateway_owner", return_value=True), patch(
            "butler.gateway.runtime_commands.handle_runtime_command",
            return_value="ran",
        ) as h:
            result = rt_cmds._cmd_runtime_run(ctx)
        assert result == "ran"
        args, _ = h.call_args
        assert args[1] == "/运行"
        assert args[2] == "job-2"


# ── owner gate ──


class TestOwnerGate:
    def test_jobs_list_has_owner_gate(self, ensure_registered):
        """/定时 加 owner gate (Sprint 17 SEC-11 扩展): jobs 名透露工作流结构.

        旧版本无 gate (Sprint 16 TST-10-5 第三批), Sprint 17 改为 owner-only.
        非 owner 返 owner_required_message; owner 调 handle_runtime_command.
        """
        from butler.gateway.owner_gate import owner_required_message

        ctx = CommandContext(
            cmd="/定时",
            arg="",
            session_key="t:s",
            platform="wechat",
            external_id="non_owner",
            orchestrator=MagicMock(),  # noqa: magicmock-no-spec — runtime command facade (orch / session_registry)
            session_registry=MagicMock(),  # noqa: magicmock-no-spec — runtime command facade (orch / session_registry)
        )
        with patch.object(rt_cmds, "is_gateway_owner", return_value=False):
            result = rt_cmds._cmd_runtime_jobs_list(ctx)
        assert result == owner_required_message(), (
            f"非 owner /定时 应被拒, 实际 {result!r}"
        )

    def test_jobs_list_owner_passes_through(self, ensure_registered):
        """owner 调 /定时 应能调 handle_runtime_command."""
        ctx = CommandContext(
            cmd="/定时",
            arg="",
            session_key="t:s",
            platform="wechat",
            external_id="owner1",
            orchestrator=MagicMock(),  # noqa: magicmock-no-spec — runtime command facade (orch / session_registry)
            session_registry=MagicMock(),  # noqa: magicmock-no-spec — runtime command facade (orch / session_registry)
        )
        with patch.object(rt_cmds, "is_gateway_owner", return_value=True), patch(
            "butler.gateway.runtime_commands.handle_runtime_command",
            return_value="jobs",
        ) as h:
            result = rt_cmds._cmd_runtime_jobs_list(ctx)
        assert h.called, "owner /定时 应能调到 handle_runtime_command"
        assert result == "jobs"

    def test_approve_run_blocked_for_non_owner(self, ensure_registered):
        from butler.gateway.owner_gate import owner_required_message

        ctx = CommandContext(
            cmd="/批准运行",
            arg="job-1",
            session_key="t:s",
            platform="wechat",
            external_id="attacker",
            orchestrator=MagicMock(),  # noqa: magicmock-no-spec — runtime command facade (orch / session_registry)
            session_registry=MagicMock(),  # noqa: magicmock-no-spec — runtime command facade (orch / session_registry)
        )
        with patch.object(rt_cmds, "is_gateway_owner", return_value=False):
            result = rt_cmds._cmd_runtime_approve_run(ctx)
        assert result == owner_required_message()

    def test_run_blocked_for_non_owner(self, ensure_registered):
        from butler.gateway.owner_gate import owner_required_message

        ctx = CommandContext(
            cmd="/运行",
            arg="job-1",
            session_key="t:s",
            platform="wechat",
            external_id="attacker",
            orchestrator=MagicMock(),  # noqa: magicmock-no-spec — runtime command facade (orch / session_registry)
            session_registry=MagicMock(),  # noqa: magicmock-no-spec — runtime command facade (orch / session_registry)
        )
        with patch.object(rt_cmds, "is_gateway_owner", return_value=False):
            result = rt_cmds._cmd_runtime_run(ctx)
        assert result == owner_required_message()


# ── inline set 缩小 ──


class TestInlineSetShrink:
    def test_3_commands_removed_from_known_inline(self):
        from tests.test_command_registry import _KNOWN_INLINE_COMMANDS

        for name in ("/定时",):  # only /定时 was in the set
            assert name not in _KNOWN_INLINE_COMMANDS

    def test_inline_set_size_leq_22(self):
        from tests.test_command_registry import _KNOWN_INLINE_COMMANDS

        assert len(_KNOWN_INLINE_COMMANDS) <= 22

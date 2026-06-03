"""Sprint 16 TST-10-5 第二批: butler.gateway.commands.memory_commands 迁移测试.

迁移 4 个 inline 命令到 registry handler:
  - /记忆图谱 (/memory-graph, /三元组)    → _cmd_memory_graph
  - /记忆待审 (/pending-memory, /待审记忆) → _cmd_memory_pending_list
  - /拒绝记忆 (/reject-memory, /拒绝)    → _cmd_memory_reject
  - /批准记忆 (/approve-memory, /批准)   → _cmd_memory_approve (含 owner gate)

覆盖:
- 静态契约: 模块导出 4 个 handler + 4 个 CommandDef + register_memory_commands
- dispatch 通过: 每个 handler 在 registry 中可查 + handler 已设置 (非 None)
- 行为: 每个 handler 委派到对应底层函数, 传递正确参数
- owner gate: /批准记忆 路径非 Owner 返 owner_required_message
- 别名: 所有 alias 也走同一 handler
- inline set 缩小: 4 个名字从 _KNOWN_INLINE_COMMANDS 移除
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from butler.gateway import command_registry
from butler.gateway.command_registry import (
    CommandContext,
    CommandDef,
    all_commands,
    dispatch,
    lookup,
)
from butler.gateway.commands import memory_commands as mem_cmds


# ── 公共 fixture: 强制 import 触发 register() ──


@pytest.fixture
def ensure_registered():
    import butler.gateway.commands  # noqa: F401
    return None


# ── 静态契约 ──


class TestStaticContract:
    def test_module_exports_4_handlers(self):
        for name in (
            "_cmd_memory_graph",
            "_cmd_memory_pending_list",
            "_cmd_memory_reject",
            "_cmd_memory_approve",
        ):
            assert hasattr(mem_cmds, name), f"memory_commands 缺 {name}"

    def test_module_exports_register_function(self):
        assert hasattr(mem_cmds, "register_memory_commands")
        assert callable(mem_cmds.register_memory_commands)

    def test_module_defines_4_command_defs(self):
        """_MEMORY_COMMANDS 列表含 4 个 CommandDef。"""
        for cmd in mem_cmds._MEMORY_COMMANDS:
            assert isinstance(cmd, CommandDef)
            assert cmd.handler is not None, f"{cmd.name} 缺 handler"

    def test_handler_attribute_set_in_registry(self, ensure_registered):
        """registry 内的 4 个命令的 handler 应被设为 _cmd_xxx (非 None)。"""
        for name in ("/记忆图谱", "/记忆待审", "/拒绝记忆", "/批准记忆"):
            cmd = lookup(name)
            assert cmd is not None, f"registry 缺 {name}"
            assert cmd.handler is not None, f"{name} 缺 handler (迁移未生效)"
            assert cmd.handler in (
                mem_cmds._cmd_memory_graph,
                mem_cmds._cmd_memory_pending_list,
                mem_cmds._cmd_memory_reject,
                mem_cmds._cmd_memory_approve,
            ), f"{name} handler 未指向新 _cmd_xxx"

    def test_register_memory_commands_is_idempotent(self):
        """重复调用 register_memory_commands() 不抛 (会覆盖同名, 不重复注册别名异常)。"""
        # 先调用一次 (模块 import 时已调)
        before = len(all_commands())
        mem_cmds.register_memory_commands()
        after = len(all_commands())
        assert before == after, "重复 register 不应增加命令数"

    def test_commands_init_imports_memory_commands(self):
        """commands/__init__ 应 import memory_commands (触发 import 副作用注册)。"""
        from butler.gateway import commands as cmds_pkg
        assert "memory_commands" in cmds_pkg.__all__
        # 子模块对象应可通过 cmds_pkg.memory_commands 访问
        assert hasattr(cmds_pkg, "memory_commands")


# ── dispatch 行为: 4 个命令的 handler 被设置 + 走 registry 路径 ──


class TestDispatch:
    def test_lookup_returns_handler(self, ensure_registered):
        for name in ("/记忆图谱", "/记忆待审", "/拒绝记忆", "/批准记忆"):
            assert lookup(name).handler is not None

    @pytest.mark.parametrize(
        "alias,canonical",
        [
            ("/memory-graph", "/记忆图谱"),
            ("/三元组", "/记忆图谱"),
            ("/pending-memory", "/记忆待审"),
            ("/待审记忆", "/记忆待审"),
            ("/reject-memory", "/拒绝记忆"),
            ("/拒绝", "/拒绝记忆"),
            ("/approve-memory", "/批准记忆"),
            ("/批准", "/批准记忆"),
        ],
    )
    def test_aliases_resolve_to_canonical_handler(self, alias, canonical, ensure_registered):
        cmd = lookup(alias)
        assert cmd is not None
        assert cmd.name == canonical
        assert cmd.handler is not None

    def test_dispatch_returns_handled_true_for_each(self, ensure_registered):
        """每个迁移命令的 dispatch() 应返 (True, str|None), 而非 (False, None)。"""
        for name in ("/记忆图谱", "/记忆待审", "/拒绝记忆", "/批准记忆"):
            orch = MagicMock()
            ctx = CommandContext(
                cmd=name,
                arg="",
                session_key="t:s",
                platform="t",
                external_id="s",
                orchestrator=orch,
                session_registry=MagicMock(),
            )
            with patch.object(mem_cmds, "_cmd_memory_approve", return_value=None) as approve_mock, \
                 patch.object(mem_cmds, "_cmd_memory_reject", return_value=None), \
                 patch.object(mem_cmds, "_cmd_memory_pending_list", return_value=None), \
                 patch.object(mem_cmds, "_cmd_memory_graph", return_value=None):
                handled, result = dispatch(ctx)
            assert handled is True, f"{name} dispatch 返 handled=False, 仍走 inline"


# ── 行为委派: handler 调用正确的底层函数 + 传 ctx 字段 ──


class TestDelegation:
    def test_memory_graph_delegates_to_format_triplet_graph(self, ensure_registered):
        from butler.gateway.memory_commands import format_memory_triplet_graph

        orch = MagicMock()
        ctx = CommandContext(
            cmd="/记忆图谱",
            arg="",
            session_key="t:s",
            platform="wechat",
            external_id="alice",
            orchestrator=orch,
            session_registry=MagicMock(),
        )
        with patch(
            "butler.gateway.memory_commands.format_memory_triplet_graph",
            return_value="graph-text",
        ) as fmt:
            result = mem_cmds._cmd_memory_graph(ctx)
        assert result == "graph-text"
        fmt.assert_called_once_with(orch)

    def test_pending_list_delegates_to_format_pending_list(self, ensure_registered):
        from butler.gateway.memory_commands import format_pending_memory_list

        orch = MagicMock()
        ctx = CommandContext(
            cmd="/记忆待审",
            arg="",
            session_key="t:s",
            platform="wechat",
            external_id="alice",
            orchestrator=orch,
            session_registry=MagicMock(),
        )
        with patch(
            "butler.gateway.memory_commands.format_pending_memory_list",
            return_value="pending-text",
        ) as fmt:
            result = mem_cmds._cmd_memory_pending_list(ctx)
        assert result == "pending-text"
        fmt.assert_called_once_with(orch)

    def test_reject_passes_canonical_cmd_and_ctx_args(self, ensure_registered):
        """/拒绝记忆 handler 委派到 handle_memory_pending_command, 强制 cmd='/拒绝记忆'。"""
        from butler.gateway.memory_commands import handle_memory_pending_command

        orch = MagicMock()
        ctx = CommandContext(
            cmd="/reject-memory",  # alias, 不应是 canonical
            arg="1",
            session_key="t:s",
            platform="wechat",
            external_id="alice",
            orchestrator=orch,
            session_registry=MagicMock(),
        )
        with patch(
            "butler.gateway.memory_commands.handle_memory_pending_command",
            return_value="rejected-1",
        ) as h:
            result = mem_cmds._cmd_memory_reject(ctx)
        assert result == "rejected-1"
        # 关键: 委派时强制使用 canonical cmd '/拒绝记忆', 不是 alias
        args, kwargs = h.call_args
        assert args[1] == "/拒绝记忆", (
            f"handler 委派应强制 canonical cmd, 实际 {args[1]!r}"
        )
        assert args[2] == "1"  # arg
        assert kwargs["platform"] == "wechat"
        assert kwargs["external_id"] == "alice"
        assert kwargs["session_key"] == "t:s"

    def test_approve_passes_canonical_cmd_and_ctx_args(self, ensure_registered):
        """/批准记忆 handler 委派到 handle_memory_pending_command, 强制 cmd='/批准记忆'。"""
        from butler.gateway.memory_commands import handle_memory_pending_command

        orch = MagicMock()
        ctx = CommandContext(
            cmd="/approve-memory",  # alias
            arg="2",
            session_key="t:s",
            platform="wechat",
            external_id="owner1",
            orchestrator=orch,
            session_registry=MagicMock(),
        )
        with patch.object(mem_cmds, "is_gateway_owner", return_value=True), patch(
            "butler.gateway.memory_commands.handle_memory_pending_command",
            return_value="approved-2",
        ) as h:
            result = mem_cmds._cmd_memory_approve(ctx)
        assert result == "approved-2"
        args, kwargs = h.call_args
        assert args[1] == "/批准记忆"
        assert args[2] == "2"
        assert kwargs["platform"] == "wechat"
        assert kwargs["external_id"] == "owner1"
        assert kwargs["session_key"] == "t:s"


# ── owner gate: /批准记忆 路径非 Owner 返 owner_required_message ──


class TestOwnerGate:
    def test_approve_returns_owner_required_message_for_non_owner(self, ensure_registered):
        from butler.gateway.owner_gate import owner_required_message

        ctx = CommandContext(
            cmd="/批准记忆",
            arg="1",
            session_key="t:s",
            platform="wechat",
            external_id="attacker",
            orchestrator=MagicMock(),
            session_registry=MagicMock(),
        )
        with patch(
            "butler.gateway.owner_gate.is_gateway_owner", return_value=False
        ):
            result = mem_cmds._cmd_memory_approve(ctx)
        assert result == owner_required_message()

    def test_approve_passes_owner_ctx_to_is_gateway_owner(self, ensure_registered):
        """is_gateway_owner 收到 platform/external_id/session_key 三个 ctx 字段。"""
        ctx = CommandContext(
            cmd="/批准记忆",
            arg="1",
            session_key="t:owner",
            platform="wechat",
            external_id="u1",
            orchestrator=MagicMock(),
            session_registry=MagicMock(),
        )
        with patch.object(mem_cmds, "is_gateway_owner", return_value=True) as gate, patch(
            "butler.gateway.memory_commands.handle_memory_pending_command",
            return_value="ok",
        ):
            mem_cmds._cmd_memory_approve(ctx)
        gate.assert_called_once_with(
            platform="wechat", external_id="u1", session_key="t:owner"
        )

    def test_reject_no_owner_gate(self, ensure_registered):
        """/拒绝记忆 不应有 owner gate — 普通用户也能 reject。"""
        ctx = CommandContext(
            cmd="/拒绝记忆",
            arg="1",
            session_key="t:s",
            platform="wechat",
            external_id="non_owner",
            orchestrator=MagicMock(),
            session_registry=MagicMock(),
        )
        with patch(
            "butler.gateway.owner_gate.is_gateway_owner", return_value=False
        ) as gate, patch(
            "butler.gateway.memory_commands.handle_memory_pending_command",
            return_value="rejected",
        ):
            result = mem_cmds._cmd_memory_reject(ctx)
        # reject 不应调用 owner gate
        gate.assert_not_called()
        assert result == "rejected"

    def test_graph_no_owner_gate(self, ensure_registered):
        """/记忆图谱 不应有 owner gate。"""
        ctx = CommandContext(
            cmd="/记忆图谱",
            arg="",
            session_key="t:s",
            platform="wechat",
            external_id="non_owner",
            orchestrator=MagicMock(),
            session_registry=MagicMock(),
        )
        with patch(
            "butler.gateway.owner_gate.is_gateway_owner", return_value=False
        ) as gate, patch(
            "butler.gateway.memory_commands.format_memory_triplet_graph",
            return_value="graph",
        ):
            result = mem_cmds._cmd_memory_graph(ctx)
        gate.assert_not_called()
        assert result == "graph"


# ── inline set 缩小: 4 个名字从 _KNOWN_INLINE_COMMANDS 移除 ──


class TestInlineSetShrink:
    def test_4_commands_removed_from_known_inline(self):
        from tests.test_command_registry import _KNOWN_INLINE_COMMANDS

        for name in ("/记忆图谱", "/记忆待审", "/拒绝记忆", "/批准记忆"):
            assert name not in _KNOWN_INLINE_COMMANDS, (
                f"{name} 应已从白名单移除 (已迁移到 registry)"
            )

    def test_inline_set_size_leq_23(self):
        """迁移 4 个后, 白名单 ≤ 27 - 4 = 23。"""
        from tests.test_command_registry import _KNOWN_INLINE_COMMANDS

        assert len(_KNOWN_INLINE_COMMANDS) <= 23, (
            f"_KNOWN_INLINE_COMMANDS 现在 {len(_KNOWN_INLINE_COMMANDS)}, "
            "应 ≤ 23 (Sprint 11 baseline 27 - Sprint 16 迁移 4)"
        )

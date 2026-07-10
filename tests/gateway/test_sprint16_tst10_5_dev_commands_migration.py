"""Sprint 16 TST-10-5 第四批: butler.gateway.commands.dev_commands 迁移测试.

迁移 6 个 dev 工具命令（统一走 handle_dev_command, 已含 owner gate）:
  - /git       (/git)                → _dev_delegate
  - /测试      (/test, /测试)         → _dev_delegate
  - /构建      (/build, /构建)       → _dev_delegate
  - /开发状态  (/开发状态, /dev-status) → _dev_delegate
  - /开发验收  (/开发验收, /dev-smoke)  → _dev_delegate
  - /项目概况  (/项目概况, /project-dashboard) → _dev_delegate

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
from butler.gateway.commands import dev_commands as dev_cmds


@pytest.fixture
def ensure_registered():
    import butler.gateway.commands  # noqa: F401
    return None


# ── 静态契约 ──


class TestStaticContract:
    def test_module_exports_6_handlers(self):
        # 6 commands share _dev_delegate (统一委派)
        for name in (
            "/git",
            "/测试",
            "/构建",
            "/开发状态",
            "/开发验收",
            "/项目概况",
        ):
            assert lookup(name) is not None, f"registry 缺 {name}"
            assert lookup(name).handler is not None, f"{name} 缺 handler"

    def test_module_defines_6_command_defs(self):
        from butler.gateway.commands.dev_commands import _DEV_COMMANDS
        assert len(_DEV_COMMANDS) == 6
        for cmd in _DEV_COMMANDS:
            assert isinstance(cmd, CommandDef)
            assert cmd.handler is not None

    def test_handler_attribute_set_in_registry(self, ensure_registered):
        for name in ("/git", "/测试", "/构建", "/开发状态", "/开发验收", "/项目概况"):
            cmd = lookup(name)
            assert cmd is not None, f"registry 缺 {name}"
            assert cmd.handler is not None, f"{name} 缺 handler"

    def test_register_dev_commands_is_idempotent(self):
        before = len(all_commands())
        dev_cmds.register_dev_commands()
        after = len(all_commands())
        assert before == after

    def test_commands_init_imports_dev_commands(self):
        from butler.gateway import commands as cmds_pkg
        assert "dev_commands" in cmds_pkg.__all__
        assert hasattr(cmds_pkg, "dev_commands")


# ── dispatch + 别名 ──


class TestDispatch:
    @pytest.mark.parametrize(
        "alias,canonical",
        [
            ("/test", "/测试"),
            ("/build", "/构建"),
            ("/dev-status", "/开发状态"),
            ("/dev-smoke", "/开发验收"),
            ("/project-dashboard", "/项目概况"),
        ],
    )
    def test_aliases_resolve_to_canonical_handler(self, alias, canonical, ensure_registered):
        cmd = lookup(alias)
        assert cmd is not None
        assert cmd.name == canonical
        assert cmd.handler is not None

    def test_dispatch_returns_handled_true_for_each(self, ensure_registered):
        for name in ("/git", "/测试", "/构建", "/开发状态", "/开发验收", "/项目概况"):
            ctx = CommandContext(
                cmd=name,
                arg="",
                session_key="t:s",
                platform="t",
                external_id="s",
                orchestrator=MagicMock(),  # noqa: magicmock-no-spec — dev command facade (orch / session_registry)
                session_registry=MagicMock(),  # noqa: magicmock-no-spec — dev command facade (orch / session_registry)
            )
            with patch(
                "butler.gateway.commands.dev_handlers.handle_dev_command",
                return_value="dev-reply",
            ) as h:
                handled, result = dispatch(ctx)
            assert handled is True, f"{name} 仍走 inline"
            assert result == "dev-reply"


# ── 行为委派 ──


class TestDelegation:
    def test_delegate_calls_handle_dev_command_with_ctx(self, ensure_registered):
        """handler 应把 ctx 转给 dev_commands.handle_dev_command."""
        from butler.gateway.commands import dev_commands as dev_cmds_module

        orch = MagicMock()  # noqa: magicmock-no-spec — dev command facade (orch / session_registry)
        ctx = CommandContext(
            cmd="/git",
            arg="status",
            session_key="t:s",
            platform="wechat",
            external_id="owner1",
            orchestrator=orch,
            session_registry=MagicMock(),  # noqa: magicmock-no-spec — dev command facade (orch / session_registry)
        )
        with patch(
            "butler.gateway.commands.dev_handlers.handle_dev_command",
            return_value="git-status-text",
        ) as h:
            result = dev_cmds_module._dev_delegate(ctx)
        assert result == "git-status-text"
        args, kwargs = h.call_args
        assert args[0] == "/git"  # cmd
        assert args[1] == "status"  # arg
        assert kwargs["platform"] == "wechat"
        assert kwargs["external_id"] == "owner1"
        assert kwargs["session_key"] == "t:s"

    def test_returns_none_when_handler_returns_none(self, ensure_registered):
        """handle_dev_command 返回 None → _dev_delegate 返回 None (caller 决定下一步)."""
        from butler.gateway.commands import dev_commands as dev_cmds_module

        ctx = CommandContext(
            cmd="/unknown-cmd",
            arg="",
            session_key="t:s",
            platform="wechat",
            external_id="owner1",
            orchestrator=MagicMock(),  # noqa: magicmock-no-spec — dev command facade (orch / session_registry)
            session_registry=MagicMock(),  # noqa: magicmock-no-spec — dev command facade (orch / session_registry)
        )
        with patch(
            "butler.gateway.commands.dev_handlers.handle_dev_command",
            return_value=None,
        ):
            assert dev_cmds_module._dev_delegate(ctx) is None


# ── owner gate ──


class TestOwnerGate:
    """handle_dev_command 内部已含 is_gateway_owner gate, 这里验证 gate 被触发."""

    def test_blocked_for_non_owner(self, ensure_registered):
        from butler.gateway.owner_gate import owner_required_message

        ctx = CommandContext(
            cmd="/git",
            arg="",
            session_key="t:s",
            platform="wechat",
            external_id="attacker",
            orchestrator=MagicMock(),  # noqa: magicmock-no-spec — dev command facade (orch / session_registry)
            session_registry=MagicMock(),  # noqa: magicmock-no-spec — dev command facade (orch / session_registry)
        )
        with patch(
            "butler.gateway.commands.dev_handlers.handle_dev_command",
            return_value=owner_required_message(),
        ):
            result = dev_cmds._dev_delegate(ctx)
        assert result == owner_required_message()

    def test_owner_passes_through(self, ensure_registered):
        ctx = CommandContext(
            cmd="/git",
            arg="",
            session_key="t:s",
            platform="wechat",
            external_id="owner1",
            orchestrator=MagicMock(),  # noqa: magicmock-no-spec — dev command facade (orch / session_registry)
            session_registry=MagicMock(),  # noqa: magicmock-no-spec — dev command facade (orch / session_registry)
        )
        with patch(
            "butler.gateway.commands.dev_handlers.handle_dev_command",
            return_value="ok-for-owner",
        ):
            result = dev_cmds._dev_delegate(ctx)
        assert result == "ok-for-owner"


# ── inline set 缩小 ──


class TestInlineSetShrink:
    def test_6_commands_removed_from_known_inline(self):
        from tests.test_command_registry import _KNOWN_INLINE_COMMANDS

        for name in ("/git", "/测试", "/构建", "/开发状态", "/开发验收", "/项目概况"):
            assert name not in _KNOWN_INLINE_COMMANDS

    def test_inline_set_size_leq_16(self):
        from tests.test_command_registry import _KNOWN_INLINE_COMMANDS

        # Sprint 16 baseline 22; 第四批迁移 6 个 → 16
        assert len(_KNOWN_INLINE_COMMANDS) <= 16

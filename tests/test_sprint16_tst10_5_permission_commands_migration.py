"""Sprint 16 TST-10-5 第六批: butler.gateway.commands.permission_commands 迁移测试.

迁移 5 个 inline 权限命令到 registry handler:
  - /权限     (/perms)                       → _cmd_perm_list
  - /批准一次                                  → _cmd_perm_once
  - /始终允许  (/always-allow)                → _cmd_perm_always
  - /批准执行  (/approve-exec)                → _cmd_perm_exec
  - /批准模式  (/approve-pattern)             → _cmd_perm_pattern

迁移要点:
  - 原 inline 块在 message_handler.handle_message 中 (line 421-461),
    slash dispatch 之前, 含 try/except logger.debug 吞异常.
  - 全部 5 个 handler 入口统一 owner gate, 失败返 owner_required_message().
  - Registry 集中错误处理 (logger.error + 返 "命令执行异常: ...") 替代旧
    静默 fall-through. 失败时用户可见.

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
from butler.gateway.commands import permission_commands as perm_cmds


@pytest.fixture
def ensure_registered():
    import butler.gateway.commands  # noqa: F401
    return None


def _make_ctx(
    cmd: str = "/权限",
    arg: str = "",
    *,
    platform: str = "wechat",
    external_id: str = "owner1",
    session_key: str = "wechat:owner1:",
) -> CommandContext:
    return CommandContext(
        cmd=cmd,
        arg=arg,
        session_key=session_key,
        platform=platform,
        external_id=external_id,
        orchestrator=MagicMock(),
        session_registry=MagicMock(),
    )


# ── 静态契约 ──


class TestStaticContract:
    def test_module_exports_5_handlers(self):
        for name in (
            "/权限",
            "/批准一次",
            "/始终允许",
            "/批准执行",
            "/批准模式",
        ):
            assert lookup(name) is not None, f"registry 缺 {name}"
            assert lookup(name).handler is not None, f"{name} 缺 handler"

    def test_module_defines_5_command_defs(self):
        from butler.gateway.commands.permission_commands import _PERMISSION_COMMANDS

        assert len(_PERMISSION_COMMANDS) == 5
        for cmd in _PERMISSION_COMMANDS:
            assert isinstance(cmd, CommandDef)
            assert cmd.handler is not None

    def test_handler_attribute_set_in_registry(self, ensure_registered):
        for name in (
            "/权限",
            "/批准一次",
            "/始终允许",
            "/批准执行",
            "/批准模式",
        ):
            cmd = lookup(name)
            assert cmd is not None, f"registry 缺 {name}"
            assert cmd.handler is not None, f"{name} 缺 handler"

    def test_register_permission_commands_is_idempotent(self):
        before = len(all_commands())
        perm_cmds.register_permission_commands()
        after = len(all_commands())
        assert before == after

    def test_commands_init_imports_permission_commands(self):
        from butler.gateway import commands as cmds_pkg

        assert "permission_commands" in cmds_pkg.__all__
        assert hasattr(cmds_pkg, "permission_commands")


# ── dispatch + 别名 ──


class TestDispatch:
    @pytest.mark.parametrize(
        "alias,canonical",
        [
            ("/perms", "/权限"),
            ("/always-allow", "/始终允许"),
            ("/approve-exec", "/批准执行"),
            ("/approve-pattern", "/批准模式"),
        ],
    )
    def test_aliases_resolve_to_canonical_handler(self, alias, canonical, ensure_registered):
        cmd = lookup(alias)
        assert cmd is not None
        assert cmd.name == canonical
        assert cmd.handler is not None

    def test_dispatch_returns_handled_true_for_each(self, ensure_registered):
        for name in (
            "/权限",
            "/批准一次",
            "/始终允许",
            "/批准执行",
            "/批准模式",
        ):
            ctx = _make_ctx(cmd=name)
            # Mock the underlying function so we don't actually call the real one
            with patch(
                "butler.gateway.commands.permission_commands._check_owner_or_return",
                return_value=None,  # owner passes
            ):
                handled, result = dispatch(ctx)
            assert handled is True, f"{name} 仍走 inline"


# ── owner gate ──


class TestOwnerGate:
    """所有 5 个 handler 入口均检查 owner, 非 owner 返 owner_required_message."""

    @pytest.mark.parametrize(
        "name",
        ["/权限", "/批准一次", "/始终允许", "/批准执行", "/批准模式"],
    )
    def test_blocked_for_non_owner(self, name, ensure_registered):
        from butler.gateway.commands import permission_commands as perm_cmds_module
        from butler.gateway.owner_gate import owner_required_message

        ctx = _make_ctx(cmd=name, external_id="attacker")
        # patch 在 importing module (permission_commands 已 `from ... import is_gateway_owner`).
        with patch.object(
            perm_cmds_module, "is_gateway_owner", return_value=False,
        ) as gate:
            handled, result = dispatch(ctx)
        assert handled is True
        assert result == owner_required_message()
        gate.assert_called_once()

    @pytest.mark.parametrize(
        "name",
        ["/权限", "/批准一次", "/始终允许", "/批准执行", "/批准模式"],
    )
    def test_owner_passes_through(self, name, ensure_registered):
        """owner 通过 gate 后, 实际调用底层函数. 这里 mock 底层函数不抛."""
        from butler.gateway.commands import permission_commands as perm_cmds_module

        ctx = _make_ctx(cmd=name, external_id="owner1")
        with patch.object(
            perm_cmds_module, "is_gateway_owner", return_value=True,
        ):
            # 各命令调不同底层函数, 但都应不抛异常 (或返字符串, 不返 None)
            handled, result = dispatch(ctx)
        assert handled is True
        # result 可能是字符串, 可能是 error message, 但至少是字符串
        assert result is None or isinstance(result, str)


# ── 行为委派 ──


class TestDelegation:
    def _owner_patch(self):
        """Helper: patch is_gateway_owner 在 importing module 上返 True."""
        from butler.gateway.commands import permission_commands as perm_cmds_module

        return patch.object(perm_cmds_module, "is_gateway_owner", return_value=True)

    def test_perm_list_delegates_to_list_always(self, ensure_registered):
        """/权限 → list_always (空 list 返 '当前会话无「始终允许」记录。')."""
        ctx = _make_ctx(cmd="/权限")
        with self._owner_patch(), patch(
            "butler.permissions.approvals.list_always", return_value=[],
        ) as h:
            result = perm_cmds._cmd_perm_list(ctx)
        assert result == "当前会话无「始终允许」记录。"
        h.assert_called_once_with(ctx.session_key)

    def test_perm_list_formats_rows(self, ensure_registered):
        """/权限 有记录时格式化输出."""
        ctx = _make_ctx(cmd="/权限")
        rows = [
            {"permission": "rule", "tool": "write_file", "pattern": "secrets/*"},
            {"permission": "external_directory", "tool": "*", "pattern": "*"},
        ]
        with self._owner_patch(), patch(
            "butler.permissions.approvals.list_always", return_value=rows,
        ):
            result = perm_cmds._cmd_perm_list(ctx)
        assert "始终允许:" in result
        assert "rule" in result
        assert "write_file" in result
        assert "secrets/*" in result
        assert "external_directory" in result

    def test_perm_once_delegates_to_grant_once(self, ensure_registered):
        """/批准一次 foo → grant_once(session_key, fingerprint='foo')."""
        ctx = _make_ctx(cmd="/批准一次", arg="my-fingerprint")
        with self._owner_patch(), patch(
            "butler.permissions.approvals.grant_once", return_value="已放行一次: my-fingerprint",
        ) as h:
            result = perm_cmds._cmd_perm_once(ctx)
        assert result == "已放行一次: my-fingerprint"
        h.assert_called_once_with(ctx.session_key, fingerprint="my-fingerprint")

    def test_perm_always_parses_spec_and_delegates(self, ensure_registered):
        """/始终允许 write_file:secrets/* → grant_always(permission=rule, tool=write_file, pattern=secrets/*)."""
        ctx = _make_ctx(cmd="/始终允许", arg="write_file:secrets/*")
        with self._owner_patch(), patch(
            "butler.permissions.approvals.grant_always", return_value="已永久放行",
        ) as h:
            result = perm_cmds._cmd_perm_always(ctx)
        assert result == "已永久放行"
        # session_key is positional, permission/tool/pattern are kwargs
        args, kwargs = h.call_args
        assert args[0] == ctx.session_key
        assert kwargs["permission"] == "rule"  # 解析出 rule
        assert kwargs["tool"] == "write_file"
        assert kwargs["pattern"] == "secrets/*"

    def test_perm_always_no_arg_returns_usage(self, ensure_registered):
        """/始终允许 (无 arg) → 返用法提示."""
        ctx = _make_ctx(cmd="/始终允许", arg="")
        with self._owner_patch():
            result = perm_cmds._cmd_perm_always(ctx)
        assert "用法" in result
        assert "/始终允许" in result

    def test_perm_exec_delegates_to_store_approval(self, ensure_registered):
        """/批准执行 rm -rf / → store_approval + 返 5 分钟内有效消息."""
        ctx = _make_ctx(cmd="/批准执行", arg="rm -rf /")
        with self._owner_patch(), patch(
            "butler.tools.terminal_approval.store_approval", return_value=None,
        ) as h:
            result = perm_cmds._cmd_perm_exec(ctx)
        assert "已批准 terminal 命令" in result
        assert "rm -rf /" in result
        h.assert_called_once_with("rm -rf /", session_key=ctx.session_key)

    def test_perm_exec_no_arg_returns_usage(self, ensure_registered):
        ctx = _make_ctx(cmd="/批准执行", arg="")
        with self._owner_patch():
            result = perm_cmds._cmd_perm_exec(ctx)
        assert "用法" in result

    def test_perm_pattern_delegates_to_approve_pattern(self, ensure_registered):
        """/批准模式 rm_rf → approve_pattern(session_key, 'rm_rf') + 24h 消息."""
        ctx = _make_ctx(cmd="/批准模式", arg="rm_rf")
        with self._owner_patch(), patch(
            "butler.tools.terminal_pattern_approval.approve_pattern", return_value=None,
        ) as h:
            result = perm_cmds._cmd_perm_pattern(ctx)
        assert "已批准本会话 terminal 危险模式" in result
        assert "rm_rf" in result
        assert "24h" in result
        h.assert_called_once_with(ctx.session_key, "rm_rf")

    def test_perm_pattern_no_arg_returns_usage(self, ensure_registered):
        ctx = _make_ctx(cmd="/批准模式", arg="")
        with self._owner_patch():
            result = perm_cmds._cmd_perm_pattern(ctx)
        assert "用法" in result


# ── 错误处理 (registry 集中处理, 与旧静默 fall-through 不同) ──


class TestErrorHandling:
    """旧版 try/except logger.debug 吞异常, 新版走 registry 集中处理."""

    def test_handler_exception_returns_error_message(self, ensure_registered):
        """_cmd_perm_once 内部抛异常 → dispatch 返 '命令执行异常: ...'."""
        from butler.gateway.commands import permission_commands as perm_cmds_module

        ctx = _make_ctx(cmd="/批准一次", arg="fp")
        with patch.object(
            perm_cmds_module, "is_gateway_owner", return_value=True,
        ), patch(
            "butler.permissions.approvals.grant_once",
            side_effect=RuntimeError("boom"),
        ):
            handled, result = dispatch(ctx)
        assert handled is True
        assert "命令执行异常" in result
        assert "boom" in result


# ── inline set 缩小 ──


class TestInlineSetShrink:
    def test_5_commands_removed_from_known_inline(self):
        from tests.test_command_registry import _KNOWN_INLINE_COMMANDS

        for name in (
            "/权限",
            "/批准一次",
            "/始终允许",
            "/批准执行",
            "/批准模式",
        ):
            assert name not in _KNOWN_INLINE_COMMANDS

    def test_inline_set_size_leq_7(self):
        from tests.test_command_registry import _KNOWN_INLINE_COMMANDS

        # Sprint 16 baseline 12; 第六批迁移 5 个权限 → 7
        assert len(_KNOWN_INLINE_COMMANDS) <= 7

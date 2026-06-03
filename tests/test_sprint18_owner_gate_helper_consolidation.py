"""Sprint 18-1: require_owner(ctx) helper 抽到 command_registry 真源.

动机: 5 个 commands/*.py (dialog/info/project/permission/lifecycle) 各自定义
_require_owner (permission 命名 _check_owner_or_return) 重复同一逻辑. 改 owner
gate 规则时必漏 1 处 (Sprint 11/12/17 三轮 SEC owner-gate 修复验证此痛点).

修复: 在 command_registry.py 提供 require_owner(ctx) 真源, 5 文件删除本地 helper,
统一调用. 行为完全等价.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from butler.gateway.command_registry import (
    CommandContext,
    all_commands,
    require_owner,
)


def _make_ctx(*, platform: str = "wechat", external_id: str = "tester",
              session_key: str = "test:sk") -> CommandContext:
    return CommandContext(
        cmd="/总览",
        arg="",
        session_key=session_key,
        platform=platform,
        external_id=external_id,
        orchestrator=None,
        session_registry=None,
    )


class TestRequireOwnerExported:
    """require_owner 必须从 command_registry 真源导出, 不再 5 文件本地定义."""

    def test_require_owner_importable_from_command_registry(self):
        """真源: command_registry.require_owner 是公开 API."""
        from butler.gateway.command_registry import require_owner as fn
        assert callable(fn)

    def test_no_local_require_owner_in_dialog_commands(self):
        """dialog_commands.py 不再有 _require_owner 本地定义."""
        from butler.gateway.commands import dialog_commands
        assert not hasattr(dialog_commands, "_require_owner"), (
            "dialog_commands._require_owner 应删除, 改用 command_registry.require_owner"
        )

    def test_no_local_require_owner_in_info_commands(self):
        from butler.gateway.commands import info_commands
        assert not hasattr(info_commands, "_require_owner")

    def test_no_local_require_owner_in_project_commands(self):
        from butler.gateway.commands import project_commands
        assert not hasattr(project_commands, "_require_owner")

    def test_no_local_require_owner_in_lifecycle_commands(self):
        from butler.gateway.commands import lifecycle_commands
        assert not hasattr(lifecycle_commands, "_require_owner")

    def test_no_local_check_owner_or_return_in_permission_commands(self):
        """permission_commands.py 命名 _check_owner_or_return, 同样删除."""
        from butler.gateway.commands import permission_commands
        assert not hasattr(permission_commands, "_check_owner_or_return")


class TestRequireOwnerBehavior:
    """行为契约: 非 owner 返 owner_required_message, owner 返 None."""

    def test_non_owner_returns_owner_required_message(self):
        ctx = _make_ctx()
        with patch(
            "butler.gateway.owner_gate.is_gateway_owner",
            return_value=False,
        ):
            result = require_owner(ctx)
        assert result is not None
        # 必须非空文本 (owner_required_message 内容由 owner_gate 决定)
        assert isinstance(result, str) and result.strip()

    def test_owner_returns_none(self):
        ctx = _make_ctx()
        with patch(
            "butler.gateway.owner_gate.is_gateway_owner",
            return_value=True,
        ):
            result = require_owner(ctx)
        assert result is None

    def test_forwards_all_three_owner_args(self):
        """必须传 platform+external_id+session_key, 与 Sprint 11 SEC 修复统一签名一致."""
        ctx = _make_ctx(platform="wechat", external_id="oX", session_key="sk:1")
        with patch(
            "butler.gateway.owner_gate.is_gateway_owner",
            return_value=True,
        ) as mock_check:
            require_owner(ctx)
        # is_gateway_owner 必须以 platform/external_id/session_key 三个 kwarg 调
        kwargs = mock_check.call_args.kwargs
        assert kwargs.get("platform") == "wechat"
        assert kwargs.get("external_id") == "oX"
        assert kwargs.get("session_key") == "sk:1"


class TestCommandRegistryImportsOwnerGate:
    """command_registry 导入 owner_gate 真源 (Sprint 18-1 引入的依赖)."""

    def test_command_registry_uses_owner_gate_is_gateway_owner(self):
        """command_registry 调 is_gateway_owner from owner_gate 真源."""
        # require_owner 内部用延迟 import 引用 owner_gate
        # patch 真正的 owner_gate.is_gateway_owner 即可
        with patch(
            "butler.gateway.owner_gate.is_gateway_owner",
            return_value=True,
        ) as mock_check:
            require_owner(_make_ctx())
        assert mock_check.called


class TestHandlerFilesImportRequireOwner:
    """5 个 handler 文件改用真源 require_owner (静态契约)."""

    @pytest.mark.parametrize(
        "module_name",
        [
            "butler.gateway.commands.dialog_commands",
            "butler.gateway.commands.info_commands",
            "butler.gateway.commands.project_commands",
            "butler.gateway.commands.lifecycle_commands",
            "butler.gateway.commands.permission_commands",
        ],
    )
    def test_handler_module_imports_require_owner(self, module_name):
        """每个 handler 模块必须 import command_registry.require_owner (真源)."""
        import importlib
        mod = importlib.import_module(module_name)
        # 静态契约: 模块级有 _require_owner_name 绑定到真源
        # 简化检查: 模块的 __dict__ 里有 'require_owner' (因为 from-import)
        assert "require_owner" in mod.__dict__, (
            f"{module_name} must `from butler.gateway.command_registry import require_owner`"
        )
        # 且这个名字指向 command_registry.require_owner (同一对象)
        from butler.gateway import command_registry
        assert mod.__dict__["require_owner"] is command_registry.require_owner


class TestRegression:
    """Sprint 17 完成的 owner gate 测试集必须全部继续通过 (无回归)."""

    def test_command_registry_has_all_commands_helper_unchanged(self):
        """all_commands() 是其他真源, 此次不动."""
        cmds = all_commands()
        assert isinstance(cmds, (list, tuple, set, frozenset))
        assert len(cmds) > 30

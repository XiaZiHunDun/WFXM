"""Sprint 19-4: registry_commands _require_owner 合并 (Sprint 19 SEC-19-4).

Sprint 19 subagent A 安全审计: registry_commands.py 自定义本地 _require_owner
(第 79-82 行), 与 command_registry.py 真源 require_owner (Sprint 18-1)
行为等价但分散. 风险:
- 改 owner gate 规则时, 需同步两处, 容易遗漏
- 静态扫描 `_require_owner` / `is_gateway_owner` 引用会显示两个真源

修复: 在 command_registry.require_owner 真源上加 kwargs 变体
require_owner_kw(platform, external_id, session_key) (registry_commands 走
legacy kwargs 路径, 不构造 CommandContext), registry_commands 删本地
_require_owner, 统一调 command_registry.require_owner_kw.

`is_gateway_owner` / `owner_required_message` 直接 import 从 owner_gate 也
从 registry_commands 中清掉, 改走 command_registry 真源.
"""

from __future__ import annotations

import ast
import inspect
from unittest.mock import patch

import pytest

from butler.gateway.commands.registry_handlers import (
    _handle_mcp,
    _handle_skills,
    handle_confirm_install_command,
)


@pytest.mark.unit
class TestRequireOwnerKwSource:
    """command_registry.require_owner_kw 是 kwargs 入口的单一真源."""

    def test_require_owner_kw_exists(self):
        from butler.gateway import command_registry

        assert hasattr(command_registry, "require_owner_kw"), (
            "command_registry 必须导出 require_owner_kw (Sprint 19-4 真源 kwargs 变体)"
        )

    def test_require_owner_kw_signature(self):
        from butler.gateway import command_registry

        sig = inspect.signature(command_registry.require_owner_kw)
        params = list(sig.parameters.keys())
        assert params == ["platform", "external_id", "session_key"], (
            f"require_owner_kw 签名不符, 实际: {params}"
        )

    def test_require_owner_kw_returns_none_for_owner(self):
        from butler.gateway import command_registry

        with patch(
            "butler.gateway.owner_gate.is_gateway_owner", return_value=True
        ):
            result = command_registry.require_owner_kw(
                platform="wechat", external_id="owner1", session_key="wx:1"
            )
        assert result is None, f"owner 应返 None, 实际: {result}"

    def test_require_owner_kw_returns_message_for_non_owner(self):
        from butler.gateway import command_registry

        with patch(
            "butler.gateway.owner_gate.is_gateway_owner", return_value=False
        ):
            result = command_registry.require_owner_kw(
                platform="wechat", external_id="u1", session_key="wx:1"
            )
        assert result is not None and ("Owner" in result or "owner" in result.lower()), (
            f"非 owner 应返 owner_required_message, 实际: {result}"
        )


@pytest.mark.unit
class TestRegistryCommandsUsesCanonicalSource:
    """registry_commands 必须用 command_registry.require_owner_kw 真源, 无本地副本."""

    def test_no_local_require_owner_function(self):
        from butler.gateway import registry_commands

        assert not hasattr(registry_commands, "_require_owner"), (
            "registry_commands 不应再有 _require_owner, 已合并到 command_registry.require_owner_kw"
        )

    def test_no_direct_owner_gate_imports(self):
        from butler.gateway import registry_commands

        src = inspect.getsource(registry_commands)
        tree = ast.parse(src)
        bad_refs: list[str] = []
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.ImportFrom)
                and node.module == "butler.gateway.owner_gate"
            ):
                bad_refs.append(
                    f"from butler.gateway.owner_gate import ... at line {node.lineno}"
                )
        assert not bad_refs, (
            f"registry_commands 不应直接 import owner_gate, 这些引用应改走 command_registry.require_owner_kw: {bad_refs}"
        )


@pytest.mark.unit
class TestRegistryCommandsBehaviorUnchanged:
    """合并后行为不变: owner / 非 owner 路径与原 _require_owner 一致."""

    def test_handle_confirm_install_non_owner_blocked(self):
        with patch(
            "butler.gateway.owner_gate.is_gateway_owner", return_value=False
        ):
            out = handle_confirm_install_command(
                "clawhub:x",
                platform="wechat",
                external_id="u1",
                session_key="wx:1",
            )
        assert "Owner" in out or "owner" in out.lower(), f"非 owner 应被拒: {out}"

    def test_handle_skills_install_non_owner_blocked(self):
        with patch(
            "butler.gateway.owner_gate.is_gateway_owner", return_value=False
        ):
            out = _handle_skills(
                "安装 clawhub:x",
                platform="wechat",
                external_id="u1",
                session_key="wx:1",
            )
        assert "Owner" in out or "owner" in out.lower(), f"非 owner 应被拒: {out}"

    def test_handle_mcp_install_non_owner_blocked(self):
        with patch(
            "butler.gateway.owner_gate.is_gateway_owner", return_value=False
        ):
            out = _handle_mcp(
                "安装 github",
                platform="wechat",
                external_id="u1",
                session_key="wx:1",
            )
        assert "Owner" in out or "owner" in out.lower(), f"非 owner 应被拒: {out}"


@pytest.mark.unit
class TestStaticContract:
    """静态契约: command_registry 是 owner gate kwargs 入口真源."""

    def test_command_registry_is_single_source(self):
        from butler.gateway import command_registry

        src = inspect.getsource(command_registry.require_owner_kw)
        assert "is_gateway_owner" in src, "require_owner_kw 内部必须调 is_gateway_owner"
        assert "owner_required_message" in src, "require_owner_kw 内部必须返 owner_required_message"

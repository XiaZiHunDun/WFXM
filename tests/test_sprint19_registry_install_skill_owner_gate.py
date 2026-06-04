"""Sprint 19-1: registry_install_skill owner gate 修复 (Sprint 19 subagent A SEC-19-A-1).

Sprint 19 subagent A 安全审计: registry_install_skill 工具的 owner 检查是 no-op.
`try: from butler.human_gate import is_owner_context` 但 `is_owner_context` 根本不存在
(0 references anywhere in butler/ + tests/, 0 hit in human_gate.py).
`except Exception: pass` 直接吞掉 ImportError, owner gate 完全失效.

攻击面: 任何 Agent 上下文触发 registry_install_skill → 任意注册表技能 (clawhub / lobehub /
github / marketplace) 可无 owner 安装, 无任何授权检查.

修复: 删 no-op try/except, 改用 butler.gateway.owner_gate.is_gateway_owner 真源.
tool 上下文从 get_current_session_key() 拿 session_key, 解析 chat_id 后做 owner 校验.
无 session_key 时 fail-closed (chat_id 为空, is_gateway_owner 返 False).
"""

from __future__ import annotations

import inspect
import json
from unittest.mock import patch

import pytest

from butler.execution_context import get_current_session_key
from butler.tools.registry_tools import (
    _tool_registry_install_skill,
    _tool_registry_propose_skill_install,
)


def _parse(result: str) -> dict:
    return json.loads(result)


@pytest.mark.unit
class TestOwnerGateNoLongerNoOp:
    """Sprint 19-1: ImportError 不再被吞, owner gate 真正生效."""

    def test_non_owner_call_returns_owner_error(self):
        """非 owner 调 registry_install_skill → 返 owner 错误, 不调 svc.install."""
        with patch(
            "butler.gateway.owner_gate.is_gateway_owner", return_value=False
        ), patch(
            "butler.registry.skill_service.SkillRegistryService.install"
        ) as mock_install:
            result = _tool_registry_install_skill("clawhub:something")

        data = _parse(result)
        assert "error" in data, f"非 owner 应返 error, 实际: {data}"
        assert mock_install.assert_not_called() or True  # 显式断言
        mock_install.assert_not_called(), "非 owner 不应调到 svc.install"

    def test_owner_call_proceeds_to_install(self):
        """owner 调 registry_install_skill → 走 svc.install, 不返 owner 错误."""
        with patch(
            "butler.gateway.owner_gate.is_gateway_owner", return_value=True
        ), patch(
            "butler.registry.skill_service.SkillRegistryService.install"
        ) as mock_install:
            mock_install.return_value = "installed-record"
            result = _tool_registry_install_skill("clawhub:something")

        data = _parse(result)
        assert data.get("ok") is True
        assert "安装" in data.get("message", "")
        mock_install.assert_called_once()

    def test_no_session_key_fails_closed(self):
        """无 session_key (chat_id 空) → owner gate fail-closed.

        is_gateway_owner 真源: 无 external_id 且无 session_key 解析时返 False.
        """
        with patch(
            "butler.gateway.owner_gate.is_gateway_owner", return_value=False
        ), patch(
            "butler.registry.skill_service.SkillRegistryService.install"
        ) as mock_install:
            result = _tool_registry_install_skill("clawhub:x")

        data = _parse(result)
        assert "error" in data
        mock_install.assert_not_called()

    def test_owner_check_does_not_swallow_exception(self):
        """owner gate 检查内部异常应传播 (fail-loud), 不应默默绕过."""
        # 模拟 is_gateway_owner 自身抛异常 (例如 owner_gate.py 损坏)
        with patch(
            "butler.gateway.owner_gate.is_gateway_owner",
            side_effect=RuntimeError("owner_gate broken"),
        ):
            with pytest.raises(RuntimeError, match="owner_gate broken"):
                _tool_registry_install_skill("clawhub:x")


@pytest.mark.unit
class TestStaticContract:
    """静态契约: 不再 import is_owner_context, 删 try/except swallow."""

    def test_no_is_owner_context_import(self):
        """registry_tools.py 不应再 import is_owner_context (根本不存在)."""
        import ast
        from butler.tools import registry_tools

        src = inspect.getsource(registry_tools)
        tree = ast.parse(src)
        bad_refs: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "butler.human_gate":
                for alias in node.names:
                    if alias.name == "is_owner_context":
                        bad_refs.append(f"from butler.human_gate import is_owner_context at line {node.lineno}")
            if isinstance(node, ast.Attribute) and node.attr == "is_owner_context":
                bad_refs.append(f"attr access is_owner_context at line {node.lineno}")
            if isinstance(node, ast.Name) and node.id == "is_owner_context":
                bad_refs.append(f"name reference is_owner_context at line {node.lineno}")
        assert not bad_refs, (
            f"is_owner_context 根本不存在, 这些引用都是 no-op: {bad_refs}"
        )

    def test_uses_is_gateway_owner_source(self):
        """修复必须用 is_gateway_owner 真源 (Sprint 18-1 owner gate 单一真源)."""
        import inspect
        from butler.tools import registry_tools

        src = inspect.getsource(registry_tools._tool_registry_install_skill)
        assert "is_gateway_owner" in src, (
            "应改用 is_gateway_owner 真源 (butler.gateway.owner_gate)"
        )


@pytest.mark.unit
class TestRegression:
    """确保不破坏 propose / search 等只读行为."""

    def test_propose_install_still_works(self):
        """_tool_registry_propose_skill_install (只读) 不应被 owner gate 影响."""
        with patch(
            "butler.registry.skill_service.SkillRegistryService.propose_install_command",
            return_value="/技能 安装 clawhub:x",
        ) as mock_cmd:
            result = _tool_registry_propose_skill_install("clawhub:x")

        data = _parse(result)
        assert data.get("action") == "propose_only"
        assert "请" in data.get("message", "") or "技能" in data.get("message", "")
        mock_cmd.assert_called_once()

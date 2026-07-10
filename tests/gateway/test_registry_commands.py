"""Tests for butler.gateway.commands.registry_handlers — skill/MCP install flows."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from butler.gateway.commands.registry_handlers import (
    handle_confirm_install_command,
    handle_registry_command,
)


@pytest.fixture
def _owner_gate():
    """Patch owner gate to always pass."""
    with patch(
        "butler.gateway.owner_gate.is_gateway_owner", return_value=True
    ):
        yield


@pytest.fixture
def _non_owner():
    """Patch owner gate to always deny."""
    with patch(
        "butler.gateway.owner_gate.is_gateway_owner", return_value=False
    ):
        yield


class TestHandleRegistryCommand:
    def test_skills_search(self, _owner_gate):
        with patch(
            "butler.gateway.commands.registry_handlers.SkillRegistryService"
        ) as MockSvc:
            svc = MockSvc.return_value
            svc.search.return_value = []
            svc.format_search_table.return_value = "无结果"
            result = handle_registry_command(
                "/技能",
                "搜索 test",
                platform="wechat",
                external_id="u1",
                session_key="s1",
            )
        assert result == "无结果"
        svc.search.assert_called_once_with("test")

    def test_skills_list_empty(self, _owner_gate):
        with patch(
            "butler.gateway.commands.registry_handlers.SkillRegistryService"
        ) as MockSvc:
            svc = MockSvc.return_value
            svc.list_installed.return_value = []
            result = handle_registry_command(
                "/技能",
                "列表",
                platform="wechat",
                external_id="u1",
                session_key="s1",
            )
        assert "无" in result

    def test_skills_list_with_entries(self, _owner_gate):
        rec = MagicMock()  # noqa: magicmock-no-spec — complex facade, spec= 收益低
        rec.name = "demo-skill"
        rec.identifier = "bundled:demo"
        rec.scan_verdict = "safe"
        with patch(
            "butler.gateway.commands.registry_handlers.SkillRegistryService"
        ) as MockSvc:
            svc = MockSvc.return_value
            svc.list_installed.return_value = [rec]
            result = handle_registry_command(
                "/技能",
                "列表",
                platform="wechat",
                external_id="u1",
                session_key="s1",
            )
        assert "demo-skill" in result

    def test_skills_inspect_not_found(self, _owner_gate):
        with patch(
            "butler.gateway.commands.registry_handlers.SkillRegistryService"
        ) as MockSvc:
            svc = MockSvc.return_value
            svc.inspect.return_value = None
            result = handle_registry_command(
                "/技能",
                "查看 missing",
                platform="wechat",
                external_id="u1",
                session_key="s1",
            )
        assert "未找到" in result

    def test_skills_install_requires_owner(self, _non_owner):
        result = handle_registry_command(
            "/技能",
            "安装 bundled:test",
            platform="wechat",
            external_id="u1",
            session_key="s1",
        )
        assert result is not None
        assert "Owner" in result or "权限" in result or "仅限" in result

    def test_unknown_command_returns_help(self, _owner_gate):
        result = handle_registry_command(
            "/技能",
            "nonsense",
            platform="wechat",
            external_id="u1",
            session_key="s1",
        )
        assert "技能目录命令" in result

    def test_unrecognized_cmd_returns_none(self, _owner_gate):
        result = handle_registry_command(
            "/unknown",
            "",
            platform="wechat",
            external_id="u1",
            session_key="s1",
        )
        assert result is None

    def test_mcp_dispatches(self, _owner_gate):
        with (
            patch(
                "butler.gateway.commands.registry_handlers.format_mcp_status_message",
                return_value="MCP OK",
            ),
            patch(
                "butler.gateway.commands.registry_handlers.resolve_workspace_for_session",
                return_value=None,
            ),
        ):
            result = handle_registry_command(
                "/mcp",
                "列表",
                platform="wechat",
                external_id="u1",
                session_key="s1",
            )
        assert result == "MCP OK"


class TestHandleConfirmInstall:
    def test_owner_required(self, _non_owner):
        result = handle_confirm_install_command(
            "bundled:test",
            platform="wechat",
            external_id="u1",
            session_key="s1",
        )
        assert "Owner" in result or "权限" in result or "仅限" in result

    def test_empty_identifier(self, _owner_gate):
        result = handle_confirm_install_command(
            "",
            platform="wechat",
            external_id="u1",
            session_key="s1",
        )
        assert "用法" in result

    def test_successful_install(self, _owner_gate):
        rec = MagicMock()  # noqa: magicmock-no-spec — complex facade, spec= 收益低
        rec.name = "test-skill"
        rec.install_path = "/path/to/skill"
        rec.scan_verdict = "safe"
        with (
            patch(
                "butler.registry.install_pending.get_pending", return_value=None
            ),
            patch(
                "butler.registry.install_pending.clear_pending"
            ),
            patch(
                "butler.gateway.commands.registry_handlers.SkillRegistryService"
            ) as MockSvc,
        ):
            svc = MockSvc.return_value
            svc.install.return_value = rec
            result = handle_confirm_install_command(
                "bundled:test",
                platform="wechat",
                external_id="u1",
                session_key="s1",
            )
        assert "已确认并安装" in result
        assert "test-skill" in result

    def test_install_failure(self, _owner_gate):
        with (
            patch(
                "butler.registry.install_pending.get_pending", return_value=None
            ),
            patch("butler.registry.install_pending.clear_pending"),
            patch(
                "butler.gateway.commands.registry_handlers.SkillRegistryService"
            ) as MockSvc,
        ):
            svc = MockSvc.return_value
            svc.install.side_effect = ValueError("not found")
            result = handle_confirm_install_command(
                "bundled:missing",
                platform="wechat",
                external_id="u1",
                session_key="s1",
            )
        assert "安装失败" in result


class TestMcpCommands:
    def test_mcp_search(self, _owner_gate):
        with patch(
            "butler.gateway.commands.registry_handlers.McpCatalogService"
        ) as MockSvc:
            svc = MockSvc.return_value
            svc.search.return_value = []
            svc.format_search.return_value = "无结果"
            result = handle_registry_command(
                "/mcp",
                "搜索 github",
                platform="wechat",
                external_id="u1",
                session_key="s1",
            )
        assert result == "无结果"

    def test_mcp_inspect_not_found(self, _owner_gate):
        with patch(
            "butler.gateway.commands.registry_handlers.McpCatalogService"
        ) as MockSvc:
            svc = MockSvc.return_value
            svc.get.return_value = None
            result = handle_registry_command(
                "/mcp",
                "查看 missing",
                platform="wechat",
                external_id="u1",
                session_key="s1",
            )
        assert "未找到" in result

    def test_mcp_install_requires_owner(self, _non_owner):
        result = handle_registry_command(
            "/mcp",
            "安装 github",
            platform="wechat",
            external_id="u1",
            session_key="s1",
        )
        assert result is not None
        assert "Owner" in result or "权限" in result or "仅限" in result

    def test_mcp_unknown_subcommand_help(self, _owner_gate):
        result = handle_registry_command(
            "/mcp",
            "nonsense",
            platform="wechat",
            external_id="u1",
            session_key="s1",
        )
        assert "MCP 目录命令" in result

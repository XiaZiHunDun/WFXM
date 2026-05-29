"""Tests for butler.gateway.command_registry."""

from butler.gateway.command_registry import (
    CommandDef,
    all_commands,
    categories,
    format_registry_help,
    lookup,
    register,
)


class TestCommandRegistry:
    def test_lookup_existing(self):
        cmd = lookup("/项目")
        assert cmd is not None
        assert cmd.name == "/项目"

    def test_lookup_alias(self):
        cmd = lookup("/projects")
        assert cmd is not None
        assert cmd.name == "/项目"

    def test_lookup_unknown(self):
        assert lookup("/nonexistent") is None

    def test_all_commands_returns_list(self):
        cmds = all_commands()
        assert len(cmds) > 30

    def test_all_commands_visibility_filter(self):
        public_cmds = all_commands(visibility="public")
        admin_cmds = all_commands(visibility="admin")
        assert len(public_cmds) > len(admin_cmds)

    def test_categories_non_empty(self):
        cats = categories()
        assert len(cats) > 0
        for cat, cmds in cats.items():
            assert len(cmds) > 0

    def test_format_registry_help_overview(self):
        result = format_registry_help()
        assert "命令" in result or "帮助" in result

    def test_format_registry_help_specific_command(self):
        result = format_registry_help("诊断")
        assert "诊断" in result

    def test_register_custom_command(self):
        cmd = CommandDef("/test_custom_xyz", (), "测试", "自定义测试命令")
        register(cmd)
        assert lookup("/test_custom_xyz") is not None

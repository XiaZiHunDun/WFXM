"""Tests for butler.gateway.help_commands."""

from butler.gateway.help_commands import format_help_text


class TestFormatHelpText:
    def test_no_topic_returns_overview(self):
        result = format_help_text()
        assert "帮助" in result or "命令" in result

    def test_valid_topic(self):
        result = format_help_text("开发")
        assert "开发" in result

    def test_alias_topic(self):
        result = format_help_text("dev")
        assert "开发" in result

    def test_unknown_topic(self):
        result = format_help_text("nonexistent_topic_xyz")
        assert "未找到" in result

    def test_all_groups_accessible(self):
        for topic in ["项目", "模型", "对话", "记忆", "权限", "开发", "日常", "管理", "规划"]:
            result = format_help_text(topic)
            assert topic in result or "帮助" in result

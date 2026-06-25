"""Tests for butler.gateway.commands.help_handlers."""

from butler.gateway.commands.help_handlers import format_help_text


class TestFormatHelpText:
    def test_no_topic_returns_overview(self):
        result = format_help_text()
        assert "/状态" in result
        assert "/简报" in result

    def test_advanced_topic(self):
        result = format_help_text("高级")
        assert "全部" in result or "主题" in result
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

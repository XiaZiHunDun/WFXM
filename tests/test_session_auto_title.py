"""Tests for butler.session.auto_title."""

from butler.session.auto_title import format_session_list, generate_session_title


class TestGenerateSessionTitle:
    def test_empty_message(self):
        assert generate_session_title("") == "新会话"

    def test_short_message(self):
        assert generate_session_title("你好") == "你好"

    def test_command_message(self):
        assert generate_session_title("/帮助").startswith("命令:")

    def test_long_message_truncated(self):
        long = "a" * 100
        result = generate_session_title(long)
        assert len(result) <= 50  # 40 + ellipsis

    def test_whitespace_normalized(self):
        result = generate_session_title("hello   world   test")
        assert "  " not in result


class TestFormatSessionList:
    def test_empty_list(self):
        result = format_session_list([])
        assert "暂无" in result

    def test_single_session(self):
        sessions = [
            {
                "title": "测试会话",
                "last_active": "2026-05-29 10:00:00",
                "last_message_preview": "你好",
            }
        ]
        result = format_session_list(sessions)
        assert "测试会话" in result
        assert "你好" in result

    def test_sorted_by_activity(self):
        sessions = [
            {"title": "旧会话", "last_active": "2026-05-28 10:00:00"},
            {"title": "新会话", "last_active": "2026-05-29 10:00:00"},
        ]
        result = format_session_list(sessions)
        new_pos = result.index("新会话")
        old_pos = result.index("旧会话")
        assert new_pos < old_pos

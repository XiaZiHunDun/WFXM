"""Tests for butler.gateway.error_cards."""

from butler.gateway.error_cards import format_error_card


class TestFormatErrorCard:
    def test_doom_loop(self):
        result = format_error_card("doom_loop", tool="terminal", count=5)
        assert "拦截" in result
        assert "terminal" in result
        assert "5" in result

    def test_permission_deny(self):
        result = format_error_card("permission_deny", tool="write_file", reason="blocked")
        assert "权限" in result
        assert "write_file" in result

    def test_delegate_timeout(self):
        result = format_error_card("delegate_timeout", role="dev", elapsed=120)
        assert "超时" in result
        assert "dev" in result

    def test_tool_error(self):
        result = format_error_card("tool_error", tool="search_files", error="rg not found")
        assert "错误" in result
        assert "search_files" in result

    def test_unknown_event(self):
        result = format_error_card("unknown_event")
        assert result is None

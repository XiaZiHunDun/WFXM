"""Tests for butler.gateway.user_errors (Sprint 2.2 rewrite)."""

from butler.gateway.user_errors import format_gateway_user_error


class TestFormatGatewayUserError:
    def test_none_exception(self):
        result = format_gateway_user_error(None)
        assert "/health" in result

    def test_connection_error(self):
        result = format_gateway_user_error(ConnectionError("refused"))
        assert "不可用" in result

    def test_permission_error(self):
        result = format_gateway_user_error(PermissionError("denied"))
        assert "权限" in result

    def test_timeout_error(self):
        result = format_gateway_user_error(TimeoutError("too slow"))
        assert "超时" in result

    def test_value_error(self):
        result = format_gateway_user_error(ValueError("bad config"))
        assert "配置" in result or "/health" in result

    def test_unknown_error(self):
        result = format_gateway_user_error(RuntimeError("unknown"))
        assert "/health" in result

    def test_keyboard_interrupt(self):
        result = format_gateway_user_error(KeyboardInterrupt())
        assert "/health" in result

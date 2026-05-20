"""User-visible gateway error messages (no paths or stack traces)."""

from __future__ import annotations


def format_gateway_user_error(exc: BaseException | None = None) -> str:
    """Return a safe message for WeChat/CLI gateway replies."""
    del exc
    return "处理失败，请稍后重试。若持续出现请发 /health 或查看网关日志。"


__all__ = ["format_gateway_user_error"]

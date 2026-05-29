"""User-visible gateway error messages (no paths or stack traces)."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_CATEGORY_MAP: list[tuple[tuple[str, ...], str]] = [
    (
        ("ConnectionError", "aiohttp.ClientError", "httpx.ConnectError",
         "httpx.ReadTimeout", "requests.ConnectionError"),
        "AI 服务暂时不可用，请稍后重试。",
    ),
    (
        ("PermissionError", "PermissionDenied"),
        "操作需要权限确认，请发 /批准 或联系管理员。",
    ),
    (
        ("TimeoutError", "asyncio.TimeoutError", "httpx.TimeoutException",
         "requests.Timeout"),
        "处理超时，请稍后重试或发 /health 检查状态。",
    ),
    (
        ("KeyError", "ValueError", "ConfigError", "EnvironmentError"),
        "系统配置异常，请联系管理员或发 /doctor 诊断。",
    ),
]


def format_gateway_user_error(exc: BaseException | None = None) -> str:
    """Return a safe classified message for WeChat/CLI gateway replies."""
    if exc is None:
        return "处理失败，请发 /health 诊断。"

    exc_type = type(exc).__name__
    exc_mro_names = {cls.__name__ for cls in type(exc).__mro__}

    for type_names, message in _CATEGORY_MAP:
        for tn in type_names:
            if tn in exc_mro_names or tn == exc_type:
                logger.info("Gateway error classified as %s: %s", tn, exc)
                return message

    logger.warning("Gateway unclassified error (%s): %s", exc_type, exc)
    return "处理失败，请发 /health 诊断。"


__all__ = ["format_gateway_user_error"]

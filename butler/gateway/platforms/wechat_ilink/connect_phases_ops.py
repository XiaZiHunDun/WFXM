"""WeChat connect phase best-effort helpers (P0-A)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from butler.core.best_effort import safe_best_effort

if TYPE_CHECKING:
    from butler.gateway.platforms.wechat_ilink import WeChatAdapter


def acquire_wechat_token_lock_safe(adapter: "WeChatAdapter") -> bool:
    """Return lock acquired; default ``True`` when lock path is unavailable."""

    def _run() -> bool:
        return bool(
            adapter._acquire_platform_lock(
                "wechat-bot-token",
                adapter._token,
                "WeChat bot token",
            )
        )

    result = safe_best_effort(
        _run,
        label="connect_phases.token_lock",
        default=True,
    )
    return bool(result) if isinstance(result, bool) else True

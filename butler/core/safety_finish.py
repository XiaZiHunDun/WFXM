"""Block tool execution when provider finish_reason indicates refusal/filter (DeerFlow subset)."""

from __future__ import annotations

from butler.env_parse import env_truthy
from butler.transport.types import NormalizedResponse

_UNSAFE_FINISH = frozenset(
    {
        "content_filter",
        "safety",
        "refusal",
        "content_filtering",
        "moderation",
    }
)


def safety_finish_guard_enabled() -> bool:
    return env_truthy("BUTLER_SAFETY_FINISH_GUARD", default=True)


def safety_finish_user_message(response: NormalizedResponse) -> str | None:
    """
    Return user-facing message when the model refused but may still list tool_calls.
    """
    if not safety_finish_guard_enabled():
        return None
    fr = str(response.finish_reason or "stop").strip().lower()
    if fr not in _UNSAFE_FINISH:
        return None
    if response.tool_calls:
        return (
            "模型因安全策略结束了本轮（finish_reason="
            f"{fr}），已忽略附带的工具调用。请换一种表述或缩小范围后重试。"
        )
    if not (response.content or "").strip():
        return f"模型因安全策略未返回可用内容（{fr}）。请调整后重试。"
    return None


__all__ = ["safety_finish_guard_enabled", "safety_finish_user_message"]

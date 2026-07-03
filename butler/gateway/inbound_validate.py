"""Gateway-side message sequence validation (主线 K P1)."""

from __future__ import annotations

from butler.env_parse import env_truthy


def inbound_sequence_validate_enabled() -> bool:
    return env_truthy("BUTLER_INBOUND_SEQUENCE_VALIDATE", default=True)


def validate_loop_messages_before_turn(messages: list[dict]) -> str | None:
    """Return user-facing error when OpenAI message sequence is invalid."""
    if not inbound_sequence_validate_enabled():
        return None
    if not messages:
        return None
    from butler.gateway.inbound_validate_ops import validate_openai_sequence_safe

    errors = validate_openai_sequence_safe(messages)
    if errors is None:
        return None
    if not errors:
        return None
    head = errors[0]
    return (
        f"会话上下文序列异常：{head}\n"
        "建议发送「/重置」清空本会话 Loop，或新开对话后再试。"
    )


__all__ = [
    "inbound_sequence_validate_enabled",
    "validate_loop_messages_before_turn",
]

"""Apply model-specific thinking protocol hints (主线 G P2 subset)."""

from __future__ import annotations

from butler.env_parse import env_truthy
from butler.transport.model_capabilities import model_supports_thinking

_THINKING_HINT = (
    "\n\n[协议] 本模型支持 extended thinking；"
    "复杂推理可先简短列出要点再作答，勿泄露冗长内部草稿。"
)


def thinking_protocol_enabled() -> bool:
    return bool(env_truthy("BUTLER_THINKING_PROTOCOL", default=False))


def maybe_append_thinking_system_hint(
    system: str,
    *,
    provider: str,
    model: str = "",
) -> str:
    if not thinking_protocol_enabled():
        return system
    if not model_supports_thinking(provider, model):
        return system
    body = str(system or "").rstrip()
    if _THINKING_HINT.strip() in body:
        return body
    return body + _THINKING_HINT


__all__ = ["maybe_append_thinking_system_hint", "thinking_protocol_enabled"]

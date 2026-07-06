"""Inbound/outbound I/O guardrails (OpenAI SDK guardrails subset, rule-first)."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

from butler.env_parse import env_truthy, int_env

_SECRET_PATTERNS = [
    re.compile(r"(?i)\b(api[_-]?key|secret|token|password)\s*[:=]\s*['\"]?\S{8,}"),
    re.compile(r"(?i)\bsk-[a-zA-Z0-9]{20,}"),
    re.compile(r"(?i)\bBearer\s+[a-zA-Z0-9._-]{20,}"),
]

_PII_PATTERNS = [
    re.compile(r"\b1[3-9]\d{9}\b"),
    re.compile(r"\b\d{17}[\dXx]\b"),
]


def io_guardrail_enabled() -> bool:
    return bool(env_truthy("BUTLER_IO_GUARDRAIL", default=True))


def io_guardrail_block_inbound() -> bool:
    return bool(env_truthy("BUTLER_IO_GUARDRAIL_BLOCK", default=False))


@dataclass(frozen=True)
class IoGuardrailResult:
    allowed: bool
    tripwire: bool = False
    reason: str = ""
    user_message: str = ""


def check_inbound_text(text: str) -> IoGuardrailResult:
    if not io_guardrail_enabled():
        return IoGuardrailResult(allowed=True)
    body = str(text or "")
    if not body.strip():
        return IoGuardrailResult(allowed=True)
    for pat in _SECRET_PATTERNS:
        if pat.search(body):
            msg = "检测到疑似密钥/令牌，请勿在聊天中发送明文凭证。"
            return IoGuardrailResult(
                allowed=not io_guardrail_block_inbound(),
                tripwire=True,
                reason="secret_pattern",
                user_message=msg,
            )
    if env_truthy("BUTLER_IO_GUARDRAIL_PII", default=False):
        for pat in _PII_PATTERNS:
            if pat.search(body):
                return IoGuardrailResult(
                    allowed=not io_guardrail_block_inbound(),
                    tripwire=True,
                    reason="pii_pattern",
                    user_message="检测到疑似个人敏感信息，已拦截。",
                )
    max_len = 0
    try:
        max_len = int_env("BUTLER_IO_GUARDRAIL_MAX_CHARS", 0)
    except ValueError:
        max_len = 0
    if max_len > 0 and len(body) > max_len:
        return IoGuardrailResult(
            allowed=not io_guardrail_block_inbound(),
            tripwire=True,
            reason="message_too_long",
            user_message=f"消息过长（>{max_len} 字），请缩短后重试。",
        )
    return IoGuardrailResult(allowed=True)


__all__ = [
    "check_inbound_text",
    "io_guardrail_block_inbound",
    "io_guardrail_enabled",
]

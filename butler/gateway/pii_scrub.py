"""Outbound PII redaction for WeChat (LangChain PIIMiddleware subset)."""

from __future__ import annotations

import os
import re
from typing import cast

from butler.env_parse import env_truthy

_PHONE = re.compile(r"(?<!\d)(?:\+?86[-\s]?)?1[3-9]\d{9}(?!\d)")
_ID18 = re.compile(r"(?<![0-9Xx])[1-9]\d{16}[\dXx](?![0-9Xx])")
_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
# sk- / sk_ API keys, OpenAI/Anthropic style (>=20 trailing alnum)
_API_KEY = re.compile(r"\bsk[-_][A-Za-z0-9]{20,}\b")
# JWT: three base64url segments separated by dots, header always starts with eyJ
_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")
# IPv4 private ranges: 10/8, 172.16/12, 192.168/16, 127/8, link-local 169.254/16
_IPV4_PRIVATE = re.compile(
    r"\b(?:"
    r"10(?:\.\d{1,3}){3}"
    r"|172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2}"
    r"|192\.168(?:\.\d{1,3}){2}"
    r"|127(?:\.\d{1,3}){3}"
    r"|169\.254(?:\.\d{1,3}){2}"
    r")\b"
)
# Bank card: 13-19 digit run, Luhn-validated
_CARD_DIGITS = re.compile(r"(?<!\d)(\d{13,19})(?!\d)")
# AWS access key id, GitHub PAT, Bearer authorization header fragments
_AWS_ACCESS_KEY = re.compile(r"\bAKIA[0-9A-Z]{16}\b")
_GITHUB_PAT = re.compile(r"\b(?:ghp_|github_pat_)[A-Za-z0-9_]{20,}\b")
_BEARER = re.compile(r"\bBearer\s+[A-Za-z0-9._-]{20,}\b", re.IGNORECASE)


def _luhn_ok(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = ord(ch) - 48
        if d < 0 or d > 9:
            return False
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def _scrub_card(match: re.Match[str]) -> str:
    if _luhn_ok(match.group(1)):
        return "[银行卡号已脱敏]"
    return match.group(0)


def outbound_pii_scrub_enabled() -> bool:
    return bool(env_truthy("BUTLER_OUTBOUND_PII_SCRUB", default=True))


def scrub_outbound_text(text: str) -> str:
    if not outbound_pii_scrub_enabled() or not text:
        return text
    out = _PHONE.sub("[手机号已脱敏]", text)
    out = _ID18.sub("[证件号已脱敏]", out)
    if env_truthy("BUTLER_OUTBOUND_PII_SCRUB_EMAIL", default=True):
        out = _EMAIL.sub("[邮箱已脱敏]", out)
    out = _API_KEY.sub("[API密钥已脱敏]", out)
    out = _JWT.sub("[JWT令牌已脱敏]", out)
    out = _BEARER.sub("[Bearer令牌已脱敏]", out)
    out = _AWS_ACCESS_KEY.sub("[云凭证已脱敏]", out)
    out = _GITHUB_PAT.sub("[GitHub令牌已脱敏]", out)
    out = _IPV4_PRIVATE.sub("[内网IP已脱敏]", out)
    out = _CARD_DIGITS.sub(_scrub_card, out)
    from butler.gateway.pii_scrub_ops import scrub_internal_leaks_safe

    return cast(str, scrub_internal_leaks_safe(out))

"""Outbound PII redaction for WeChat (LangChain PIIMiddleware subset)."""

from __future__ import annotations

import os
import re

from butler.env_parse import env_truthy

_PHONE = re.compile(r"(?<!\d)(?:\+?86[-\s]?)?1[3-9]\d{9}(?!\d)")
_ID18 = re.compile(r"(?<![0-9Xx])[1-9]\d{16}[\dXx](?![0-9Xx])")
_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")


def outbound_pii_scrub_enabled() -> bool:
    return env_truthy("BUTLER_OUTBOUND_PII_SCRUB", default=True)


def scrub_outbound_text(text: str) -> str:
    if not outbound_pii_scrub_enabled() or not text:
        return text
    out = _PHONE.sub("[手机号已脱敏]", text)
    out = _ID18.sub("[证件号已脱敏]", out)
    if os.getenv("BUTLER_OUTBOUND_PII_SCRUB_EMAIL", "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    ):
        out = _EMAIL.sub("[邮箱已脱敏]", out)
    return out

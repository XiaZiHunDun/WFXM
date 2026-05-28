"""API error classification for Butler LLM failover and recovery.

Simplified port of Hermes ``agent/error_classifier.py`` — maps exceptions to
recovery actions (retry, compress, fallback, abort).
"""

from __future__ import annotations

import enum
import re
from dataclasses import dataclass
from typing import Any


class FailoverReason(str, enum.Enum):
    auth = "auth"
    billing = "billing"
    rate_limit = "rate_limit"
    overloaded = "overloaded"
    server_error = "server_error"
    timeout = "timeout"
    context_overflow = "context_overflow"
    payload_too_large = "payload_too_large"
    model_not_found = "model_not_found"
    format_error = "format_error"
    unknown = "unknown"


@dataclass
class ClassifiedError:
    reason: FailoverReason
    status_code: int | None = None
    message: str = ""
    retryable: bool = True
    should_compress: bool = False
    should_fallback: bool = False


_BILLING = (
    "insufficient credits", "insufficient_quota", "payment required",
    "credit balance", "billing", "account is deactivated",
)
_RATE_LIMIT = (
    "rate limit", "rate_limit", "too many requests", "429",
    "throttled", "resource_exhausted",
)
_CONTEXT = (
    "context length", "context window", "token limit", "too many tokens",
    "maximum context", "prompt is too long", "max_model_len",
    "上下文长度", "超过最大长度",
)
_PAYLOAD = ("request entity too large", "payload too large", "413")


def _extract_status_code(error: Exception) -> int | None:
    for attr in ("status_code", "http_status", "code"):
        val = getattr(error, attr, None)
        if isinstance(val, int):
            return val
    m = re.search(r"\b(4\d{2}|5\d{2})\b", str(error))
    if m:
        return int(m.group(1))
    return None


def _error_text(error: Exception) -> str:
    parts = [str(error).lower()]
    body = getattr(error, "body", None)
    if isinstance(body, dict):
        err = body.get("error", body)
        if isinstance(err, dict):
            parts.append(str(err.get("message", "")).lower())
        else:
            parts.append(str(body).lower())
    return " ".join(parts)


def classify_api_error(
    error: Exception,
    *,
    provider: str = "",
    model: str = "",
) -> ClassifiedError:
    """Classify an API error and suggest recovery."""
    status = _extract_status_code(error)
    msg = _error_text(error)
    etype = type(error).__name__

    if status is None and etype == "RateLimitError":
        status = 429

    def _ce(reason: FailoverReason, **kw: Any) -> ClassifiedError:
        return ClassifiedError(reason=reason, status_code=status, message=str(error)[:500], **kw)

    if any(p in msg for p in _CONTEXT):
        return _ce(FailoverReason.context_overflow, should_compress=True, should_fallback=False, retryable=True)

    if status == 404 or "model not found" in msg or "does not exist" in msg:
        return _ce(FailoverReason.model_not_found, should_fallback=True, retryable=False)

    if status in (401, 403) or "invalid api key" in msg or "authentication" in msg:
        return _ce(FailoverReason.auth, should_fallback=True, retryable=True)

    if status == 402 or any(p in msg for p in _BILLING):
        return _ce(FailoverReason.billing, should_fallback=True, retryable=False)

    if status == 429 or any(p in msg for p in _RATE_LIMIT):
        return _ce(FailoverReason.rate_limit, should_fallback=True, retryable=True)

    if status in (503, 529) or "overloaded" in msg:
        return _ce(FailoverReason.overloaded, retryable=True)

    if status in (500, 502) or "internal server" in msg:
        return _ce(FailoverReason.server_error, retryable=True)

    if status == 413 or any(p in msg for p in _PAYLOAD):
        return _ce(FailoverReason.payload_too_large, should_compress=True, retryable=True)

    if status == 400 and "bad request" in msg:
        return _ce(FailoverReason.format_error, retryable=False)

    if etype in ("Timeout", "TimeoutError", "ConnectTimeout", "ReadTimeout") or "timeout" in msg:
        return _ce(FailoverReason.timeout, retryable=True)

    if "connection" in msg or "network" in msg or etype in ("ConnectionError", "APIConnectionError"):
        return _ce(FailoverReason.timeout, retryable=True)

    return _ce(FailoverReason.unknown, retryable=True)

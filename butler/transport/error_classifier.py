"""API error classification for Butler LLM failover and recovery.

Maps exceptions to recovery actions (retry, compress, fallback, abort)
with a priority-ordered classification pipeline. Based on Hermes
``agent/error_classifier.py`` with provider-specific patterns.
"""

from __future__ import annotations

import enum
import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


class FailoverReason(str, enum.Enum):
    # Authentication / authorization
    auth = "auth"
    auth_permanent = "auth_permanent"

    # Billing / quota
    billing = "billing"
    rate_limit = "rate_limit"
    upstream_rate_limit = "upstream_rate_limit"

    # Server-side
    overloaded = "overloaded"
    server_error = "server_error"

    # Transport
    timeout = "timeout"
    ssl_cert_verification = "ssl_cert_verification"

    # Context / payload
    context_overflow = "context_overflow"
    payload_too_large = "payload_too_large"
    image_too_large = "image_too_large"

    # Model / provider policy
    model_not_found = "model_not_found"
    provider_policy_blocked = "provider_policy_blocked"
    content_policy_blocked = "content_policy_blocked"

    # Request format
    format_error = "format_error"
    multimodal_tool_content_unsupported = "multimodal_tool_content_unsupported"

    # Provider-specific
    thinking_signature = "thinking_signature"
    long_context_tier = "long_context_tier"
    llama_cpp_grammar_pattern = "llama_cpp_grammar_pattern"

    # Catch-all
    unknown = "unknown"


@dataclass
class ClassifiedError:
    reason: FailoverReason
    status_code: Optional[int] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    message: str = ""
    error_context: Dict[str, Any] = field(default_factory=dict)

    retryable: bool = True
    should_compress: bool = False
    should_rotate_credential: bool = False
    should_fallback: bool = False

    @property
    def is_auth(self) -> bool:
        return self.reason in {FailoverReason.auth, FailoverReason.auth_permanent}


# ── Error patterns ──────────────────────────────────────────────────────────────

_BILLING_PATTERNS = (
    "insufficient credits", "insufficient_quota", "insufficient balance",
    "credit balance", "credits exhausted", "payment required",
    "billing hard limit", "account is deactivated", "out of funds",
    "balance_depleted", "model_not_supported_on_free_tier",
)

_RATE_LIMIT_PATTERNS = (
    "rate limit", "rate_limit", "too many requests", "throttled",
    "resource_exhausted", "throttlingexception", "servicequotaexceededexception",
)

_OVERLOADED_PATTERNS = (
    "overloaded", "temporarily overloaded", "service is temporarily overloaded",
    "server is overloaded", "at capacity", "over capacity",
)

_CONTEXT_OVERFLOW_PATTERNS = (
    "context length", "context window", "token limit", "too many tokens",
    "maximum context", "prompt is too long", "max_model_len",
    "上下文长度", "超过最大长度", "context length exceeded",
    "max_tokens", "prompt length", "input is too long",
)

_PAYLOAD_TOO_LARGE_PATTERNS = (
    "request entity too large", "payload too large", "error code: 413",
)

_IMAGE_TOO_LARGE_PATTERNS = (
    "image exceeds", "image too large", "image_too_large",
    "image size exceeds", "image dimensions exceed",
)

_MODEL_NOT_FOUND_PATTERNS = (
    "is not a valid model", "invalid model", "model not found",
    "model_not_found", "does not exist", "unknown model", "unsupported model",
)

_REQUEST_VALIDATION_PATTERNS = (
    "unknown parameter", "unsupported parameter", "unrecognized request argument",
    "invalid_request_error",
)

_PROVIDER_POLICY_BLOCKED_PATTERNS = (
    "no endpoints available matching your guardrail",
    "no endpoints available matching your data policy",
)

_CONTENT_POLICY_BLOCKED_PATTERNS = (
    "flagged for possible cybersecurity risk", "trusted access for cyber",
    "violates our usage policies", "violates openai's usage policies",
    "your request was flagged by", "prompt was flagged by our safety",
    "content_filter", "responsibleaipolicyviolation",
)

_AUTH_PATTERNS = (
    "invalid api key", "invalid_api_key", "authentication", "unauthorized",
    "forbidden", "invalid token", "token expired", "token revoked", "access denied",
)

_MULTIMODAL_TOOL_CONTENT_PATTERNS = (
    "text is not set", "tool message content must be a string",
    "tool content must be a string", "expected string, got list",
    "expected string, got array", "tool_call.content must be string",
)

_SSL_CERT_VERIFY_PATTERNS = (
    "certificate verify failed", "certificate_verify_failed",
    "unable to get local issuer certificate", "self-signed certificate",
    "certificate has expired", "hostname mismatch",
)

_SSL_TRANSIENT_PATTERNS = (
    "bad record mac", "ssl alert", "tls alert", "ssl handshake failure",
    "[ssl:", "bad_record_mac",
)

_SERVER_DISCONNECT_PATTERNS = (
    "server disconnected", "peer closed connection", "connection reset by peer",
    "network connection lost", "unexpected eof", "incomplete chunked read",
)

_TRANSPORT_ERROR_TYPES = frozenset({
    "ReadTimeout", "ConnectTimeout", "PoolTimeout",
    "ConnectError", "RemoteProtocolError", "ConnectionError",
    "ConnectionResetError", "ConnectionAbortedError", "BrokenPipeError",
    "TimeoutError", "ReadError", "ServerDisconnectedError",
    "SSLError", "SSLZeroReturnError", "APIConnectionError", "APITimeoutError",
})


def _extract_status_code(error: Exception) -> Optional[int]:
    for attr in ("status_code", "http_status", "code"):
        val = getattr(error, attr, None)
        if isinstance(val, int):
            return val
    m = re.search(r"\b(4\d{2}|5\d{2})\b", str(error))
    if m:
        return int(m.group(1))
    return None


def _extract_error_body(error: Exception) -> Any:
    for attr in ("body", "response", "error"):
        val = getattr(error, attr, None)
        if isinstance(val, (dict, str)):
            if isinstance(val, str):
                try:
                    return json.loads(val)
                except (json.JSONDecodeError, TypeError):
                    return {"message": val}
            return val
    return {}


def _extract_error_code(body: dict) -> str:
    if not isinstance(body, dict):
        return ""
    err = body.get("error", body)
    if isinstance(err, dict):
        return str(err.get("code", "") or "")
    return ""


def _extract_message(error: Exception, body: Any) -> str:
    msg = str(error)[:500]
    if isinstance(body, dict):
        err = body.get("error", body)
        if isinstance(err, dict):
            body_msg = err.get("message")
            if body_msg and body_msg not in msg:
                msg = f"{msg} | {str(body_msg)[:200]}"
    return msg


def _error_text(error: Exception) -> str:
    """Build comprehensive error message string for pattern matching."""
    _raw_msg = str(error).lower()
    _body_msg = ""
    _metadata_msg = ""
    body = _extract_error_body(error)

    if isinstance(body, dict):
        _err_obj = body.get("error", {})
        if isinstance(_err_obj, dict):
            _body_msg = str(_err_obj.get("message") or "").lower()
            _metadata = _err_obj.get("metadata", {})
            if isinstance(_metadata, dict):
                _raw_json = _metadata.get("raw") or ""
                if isinstance(_raw_json, str) and _raw_json.strip():
                    try:
                        _inner = json.loads(_raw_json)
                        if isinstance(_inner, dict):
                            _inner_err = _inner.get("error", {})
                            if isinstance(_inner_err, dict):
                                _metadata_msg = str(_inner_err.get("message") or "").lower()
                    except (json.JSONDecodeError, TypeError):
                        pass
        if not _body_msg:
            _body_msg = str(body.get("message") or "").lower()

    parts = [_raw_msg]
    if _body_msg and _body_msg not in _raw_msg:
        parts.append(_body_msg)
    if _metadata_msg and _metadata_msg not in _raw_msg and _metadata_msg not in _body_msg:
        parts.append(_metadata_msg)
    return " ".join(parts)


def _is_openrouter_upstream_error(body: dict, provider: str) -> bool:
    if provider.lower() != "openrouter":
        return False
    if not isinstance(body, dict):
        return False
    err = body.get("error", {})
    return isinstance(err, dict) and "provider returned error" in str(err.get("message", "")).lower()


def _extract_upstream_provider_name(body: dict) -> Optional[str]:
    if not isinstance(body, dict):
        return None
    err = body.get("error", {})
    if isinstance(err, dict):
        meta = err.get("metadata", {})
        if isinstance(meta, dict):
            return str(meta.get("upstream", "") or "")
    return None


def classify_api_error(
    error: Exception,
    *,
    provider: str = "",
    model: str = "",
    approx_tokens: int = 0,
    context_length: int = 200000,
    num_messages: int = 0,
) -> ClassifiedError:
    """Classify an API error into a structured recovery recommendation.

    Priority-ordered pipeline:
      1. Provider-specific patterns (content policy, thinking signatures)
      2. HTTP status code + message-aware refinement
      3. Error code classification
      4. Message pattern matching
      5. SSL/TLS transient alert patterns → retry as timeout
      6. Server disconnect + large session → context overflow
      7. Transport error heuristics
      8. Fallback: unknown (retryable with backoff)
    """
    status_code = _extract_status_code(error)
    error_type = type(error).__name__

    if status_code is None and error_type == "RateLimitError":
        status_code = 429

    body = _extract_error_body(error)
    error_code = _extract_error_code(body)
    error_msg = _error_text(error)
    provider_lower = provider.strip().lower()
    model_lower = model.strip().lower()

    def _result(reason: FailoverReason, **overrides: Any) -> ClassifiedError:
        defaults = {
            "reason": reason,
            "status_code": status_code,
            "provider": provider,
            "model": model,
            "message": _extract_message(error, body),
        }
        defaults.update(overrides)
        return ClassifiedError(**defaults)

    # ── 1. Provider-specific patterns (highest priority) ──────────────────────

    # Content policy / safety-filter block (deterministic, don't retry)
    if any(p in error_msg for p in _CONTENT_POLICY_BLOCKED_PATTERNS):
        return _result(FailoverReason.content_policy_blocked, retryable=False, should_fallback=True)

    # Anthropic thinking block recovery (400)
    if (
        status_code == 400
        and "thinking" in error_msg
        and ("signature" in error_msg or "cannot be modified" in error_msg)
    ):
        return _result(FailoverReason.thinking_signature, retryable=True, should_compress=False)

    # Anthropic long-context tier gate (429)
    if status_code == 429 and "extra usage" in error_msg and "long context" in error_msg:
        return _result(FailoverReason.long_context_tier, retryable=True, should_compress=True)

    # llama.cpp grammar pattern error (400)
    if (
        status_code == 400
        and ("error parsing grammar" in error_msg or "json-schema-to-grammar" in error_msg)
    ):
        return _result(FailoverReason.llama_cpp_grammar_pattern, retryable=True, should_compress=False)

    # ── 2. HTTP status code classification ─────────────────────────────────────

    if status_code is not None:
        if status_code == 401:
            return _result(
                FailoverReason.auth,
                retryable=False,
                should_rotate_credential=True,
                should_fallback=True,
            )

        if status_code == 403:
            if any(p in error_msg for p in _BILLING_PATTERNS) or "spending limit" in error_msg:
                return _result(FailoverReason.billing, retryable=False, should_fallback=True)
            return _result(FailoverReason.auth, retryable=False, should_fallback=True)

        if status_code == 402:
            return _result(FailoverReason.billing, retryable=False, should_fallback=True)

        if status_code == 404:
            if any(p in error_msg for p in _BILLING_PATTERNS):
                return _result(FailoverReason.billing, retryable=False, should_fallback=True)
            if any(p in error_msg for p in _PROVIDER_POLICY_BLOCKED_PATTERNS):
                return _result(FailoverReason.provider_policy_blocked, retryable=False)
            if any(p in error_msg for p in _MODEL_NOT_FOUND_PATTERNS):
                return _result(FailoverReason.model_not_found, should_fallback=True, retryable=False)
            return _result(FailoverReason.unknown, retryable=True)

        if status_code == 413:
            return _result(FailoverReason.payload_too_large, retryable=True, should_compress=True)

        if status_code == 429:
            if any(p in error_msg for p in _OVERLOADED_PATTERNS):
                return _result(FailoverReason.overloaded, retryable=True)
            if _is_openrouter_upstream_error(body, provider_lower):
                upstream_provider = _extract_upstream_provider_name(body)
                ctx = {"upstream_provider": upstream_provider} if upstream_provider else {}
                return _result(
                    FailoverReason.upstream_rate_limit,
                    retryable=True,
                    should_rotate_credential=False,
                    should_fallback=True,
                    error_context=ctx,
                )
            return _result(FailoverReason.rate_limit, retryable=True, should_fallback=True)

        if status_code == 400:
            if any(p in error_msg for p in _IMAGE_TOO_LARGE_PATTERNS):
                return _result(FailoverReason.image_too_large, retryable=True, should_compress=True)
            if any(p in error_msg for p in _MULTIMODAL_TOOL_CONTENT_PATTERNS):
                return _result(FailoverReason.multimodal_tool_content_unsupported, retryable=True)
            if any(p in error_msg for p in _REQUEST_VALIDATION_PATTERNS):
                return _result(FailoverReason.format_error, retryable=False, should_fallback=True)
            if any(p in error_msg for p in _CONTEXT_OVERFLOW_PATTERNS):
                return _result(FailoverReason.context_overflow, retryable=True, should_compress=True)
            return _result(FailoverReason.format_error, retryable=False)

        if status_code in {500, 502}:
            if any(p in error_msg for p in _REQUEST_VALIDATION_PATTERNS):
                return _result(FailoverReason.format_error, retryable=False, should_fallback=True)
            if any(p in error_msg for p in _CONTEXT_OVERFLOW_PATTERNS):
                return _result(FailoverReason.context_overflow, retryable=True, should_compress=True)
            return _result(FailoverReason.server_error, retryable=True)

        if status_code in {503, 529}:
            if any(p in error_msg for p in _CONTEXT_OVERFLOW_PATTERNS):
                return _result(FailoverReason.context_overflow, retryable=True, should_compress=True)
            return _result(FailoverReason.overloaded, retryable=True)

        if status_code == 408:
            return _result(FailoverReason.timeout, retryable=True)

    # ── 3. Error code classification ───────────────────────────────────────────

    if error_code:
        if error_code.lower() in {"invalid_request_error", "unknown_parameter", "unsupported_parameter"}:
            return _result(FailoverReason.format_error, retryable=False)
        if error_code.lower() in {"insufficient_quota", "billing_not_active", "payment_required"}:
            return _result(FailoverReason.billing, retryable=False, should_fallback=True)

    # ── 4. Message pattern matching (no status code) ───────────────────────────

    if any(p in error_msg for p in _CONTEXT_OVERFLOW_PATTERNS):
        return _result(FailoverReason.context_overflow, should_compress=True, retryable=True)

    if any(p in error_msg for p in _BILLING_PATTERNS):
        return _result(FailoverReason.billing, retryable=False, should_fallback=True)

    if any(p in error_msg for p in _RATE_LIMIT_PATTERNS):
        return _result(FailoverReason.rate_limit, retryable=True, should_fallback=True)

    if any(p in error_msg for p in _OVERLOADED_PATTERNS):
        return _result(FailoverReason.overloaded, retryable=True)

    if any(p in error_msg for p in _MODEL_NOT_FOUND_PATTERNS):
        return _result(FailoverReason.model_not_found, should_fallback=True, retryable=False)

    if any(p in error_msg for p in _PAYLOAD_TOO_LARGE_PATTERNS):
        return _result(FailoverReason.payload_too_large, should_compress=True, retryable=True)

    if any(p in error_msg for p in _AUTH_PATTERNS):
        return _result(FailoverReason.auth, should_fallback=True, retryable=True)

    if "timed out" in error_msg or "deadline exceeded" in error_msg:
        return _result(FailoverReason.timeout, retryable=True)

    # ── 5. SSL certificate verification failures → fail fast ───────────────────

    if any(p in error_msg for p in _SSL_CERT_VERIFY_PATTERNS):
        return _result(FailoverReason.ssl_cert_verification, retryable=False, should_fallback=False)

    # ── 5b. SSL/TLS transient errors → retry as timeout ────────────────────────

    if any(p in error_msg for p in _SSL_TRANSIENT_PATTERNS):
        return _result(FailoverReason.timeout, retryable=True)

    # ── 6. Server disconnect + large session → context overflow ────────────────

    is_disconnect = any(p in error_msg for p in _SERVER_DISCONNECT_PATTERNS)
    if is_disconnect and not status_code:
        is_large = approx_tokens > context_length * 0.6 or (
            context_length <= 256000 and (approx_tokens > 120000 or num_messages > 200)
        )
        if is_large:
            return _result(FailoverReason.context_overflow, retryable=True, should_compress=True)
        return _result(FailoverReason.timeout, retryable=True)

    # ── 7. Transport / timeout heuristics ──────────────────────────────────────

    if error_type in _TRANSPORT_ERROR_TYPES or isinstance(error, (TimeoutError, ConnectionError, OSError)):
        return _result(FailoverReason.timeout, retryable=True)

    # ── 8. Fallback: unknown ────────────────────────────────────────────────────

    return _result(FailoverReason.unknown, retryable=True)

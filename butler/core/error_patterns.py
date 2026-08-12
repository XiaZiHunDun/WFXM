"""Error pattern tables used by the error classifier.

Centralises all regex/substring patterns for error classification so they
can be audited and extended independently from the classification logic.
"""

from __future__ import annotations

__all__ = [
    "_AUTH_PATTERNS",
    "_BILLING_PATTERNS",
    "_CONTENT_POLICY_BLOCKED_PATTERNS",
    "_CONTEXT_OVERFLOW_PATTERNS",
    "_FORMAT_ERROR_PATTERNS",
    "_IMAGE_TOO_LARGE_PATTERNS",
    "_LOCAL_PROCESSING_ERROR_PATTERNS",
    "_MODEL_NOT_FOUND_PATTERNS",
    "_OVERLOADED_PATTERNS",
    "_PAYLOAD_TOO_LARGE_PATTERNS",
    "_PROVIDER_POLICY_BLOCKED_PATTERNS",
    "_RATE_LIMIT_PATTERNS",
    "_SSL_CERT_VERIFY_PATTERNS",
    "_TRANSPORT_ERROR_TYPES",
]


_BILLING_PATTERNS: tuple[str, ...] = (
    "insufficient credits",
    "insufficient_quota",
    "insufficient balance",
    "credit balance",
    "credits exhausted",
    "payment required",
    "billing hard limit",
    "account is deactivated",
    "out of funds",
    "balance_depleted",
    "model_not_supported_on_free_tier",
    "spending limit",
)

_RATE_LIMIT_PATTERNS: tuple[str, ...] = (
    "rate limit",
    "rate_limit",
    "too many requests",
    "throttled",
    "resource_exhausted",
    "throttlingexception",
    "servicequotaexceededexception",
)

_OVERLOADED_PATTERNS: tuple[str, ...] = (
    "overloaded",
    "temporarily overloaded",
    "service is temporarily overloaded",
    "server is overloaded",
    "at capacity",
    "over capacity",
)

_CONTEXT_OVERFLOW_PATTERNS: tuple[str, ...] = (
    "context length",
    "context window",
    "token limit",
    "too many tokens",
    "maximum context",
    "prompt is too long",
    "max_model_len",
    "上下文长度",
    "超过最大长度",
    "context length exceeded",
    "max_tokens",
    "prompt length",
    "input is too long",
    "context_overflow",
)

_PAYLOAD_TOO_LARGE_PATTERNS: tuple[str, ...] = (
    "request entity too large",
    "payload too large",
    "error code: 413",
    "file_too_large",
)

_IMAGE_TOO_LARGE_PATTERNS: tuple[str, ...] = (
    "image exceeds",
    "image too large",
    "image_too_large",
    "image size exceeds",
    "image dimensions exceed",
    "image is too large",
)

_MODEL_NOT_FOUND_PATTERNS: tuple[str, ...] = (
    "is not a valid model",
    "invalid model",
    "model not found",
    "model_not_found",
    "does not exist",
    "unknown model",
    "unsupported model",
    "no such model",
)

_PROVIDER_POLICY_BLOCKED_PATTERNS: tuple[str, ...] = (
    "no endpoints available matching your guardrail",
    "no endpoints available matching your data policy",
    "policy restricted",
)

_CONTENT_POLICY_BLOCKED_PATTERNS: tuple[str, ...] = (
    "flagged for possible cybersecurity risk",
    "trusted access for cyber",
    "violates our usage policies",
    "violates openai's usage policies",
    "your request was flagged by",
    "prompt was flagged by our safety",
    "content_filter",
    "responsibleaipolicyviolation",
    "moderation",
)

_AUTH_PATTERNS: tuple[str, ...] = (
    "invalid api key",
    "invalid_api_key",
    "authentication",
    "unauthorized",
    "forbidden",
    "invalid token",
    "token expired",
    "token revoked",
    "access denied",
    "incorrect api key",
    "api key not found",
    "api key disabled",
    "api key expired",
    "api key deleted",
)

_FORMAT_ERROR_PATTERNS: tuple[str, ...] = (
    "unknown parameter",
    "unsupported parameter",
    "unrecognized request argument",
    "invalid_request_error",
    "invalid parameter",
    "invalid request",
    "schema mismatch",
)

_SSL_CERT_VERIFY_PATTERNS: tuple[str, ...] = (
    "certificate verify failed",
    "certificate_verify_failed",
    "unable to get local issuer certificate",
    "self-signed certificate",
    "certificate has expired",
    "hostname mismatch",
    "ssl: certificate_verify_failed",
    "tls: certificate_verify_failed",
)

_TRANSPORT_ERROR_TYPES: frozenset[str] = frozenset({
    "ReadTimeout",
    "ConnectTimeout",
    "PoolTimeout",
    "ConnectError",
    "RemoteProtocolError",
    "ConnectionError",
    "ConnectionResetError",
    "ConnectionAbortedError",
    "BrokenPipeError",
    "TimeoutError",
    "ReadError",
    "ServerDisconnectedError",
    "SSLError",
    "SSLZeroReturnError",
    "APIConnectionError",
    "APITimeoutError",
    "AsyncClientError",
    "ClientConnectorError",
    "ClientResponseError",
})

_LOCAL_PROCESSING_ERROR_PATTERNS: tuple[str, ...] = (
    "object of type",
    "is not json serializable",
    "cannot encode",
    "typeerror: ",
    "attributeerror: ",
    "valueerror: ",
    "keyerror: ",
    "runtimeerror: ",
    "recursionerror",
    "cannot pickle",
    "not supported between",
    "expected string or bytes-like",
    "must be str, not",
    "got an invalid value",
    "is not a valid",
    "must be of type",
    "is not iterable",
    "argument 1 must be",
    "takes",
    "positional argument but",
    "positional arguments but",
    "expected",
)

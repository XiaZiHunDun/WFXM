"""Structured API error classification for smart failover and recovery.

Maps arbitrary API exceptions to a :class:`ClassifiedError` that annotates
the failure with a :class:`FailoverReason` and high-level recovery hints
(should we retry? rotate credentials? fall back to another model? compress
the context?).  The classifier is intentionally provider-agnostic: it
inspects HTTP status codes, error-code bodies and message fragments so
that a single pipeline works for both sync and async transports and for
every upstream provider we integrate with.

The module is deliberately stdlib-only plus lightweight helpers from
``butler.utilities`` so it can be imported from very early stages of
the boot process (cli, gateway, orchestrator) without pulling heavy
transport-layer dependencies.
"""

from __future__ import annotations

import enum
import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

__all__ = [
    "FailoverReason",
    "ClassifiedError",
    "classify_api_error",
    "is_retryable",
    "is_local_processing_error",
]

from butler.core.error_patterns import (
    _AUTH_PATTERNS,
    _BILLING_PATTERNS,
    _CONTENT_POLICY_BLOCKED_PATTERNS,
    _CONTEXT_OVERFLOW_PATTERNS,
    _FORMAT_ERROR_PATTERNS,
    _IMAGE_TOO_LARGE_PATTERNS,
    _LOCAL_PROCESSING_ERROR_PATTERNS,
    _MODEL_NOT_FOUND_PATTERNS,
    _OVERLOADED_PATTERNS,
    _PAYLOAD_TOO_LARGE_PATTERNS,
    _PROVIDER_POLICY_BLOCKED_PATTERNS,
    _RATE_LIMIT_PATTERNS,
    _SSL_CERT_VERIFY_PATTERNS,
    _TRANSPORT_ERROR_TYPES,
)


# ──────────────────────────────────────────────────────────────────────
# 1. Error taxonomy
# ──────────────────────────────────────────────────────────────────────


class FailoverReason(str, enum.Enum):
    """Normalised failure reasons used by the failover pipeline.

    The enum members are grouped by the kind of recovery they invite:

    * **auth / auth_permanent** – credential problems.  ``auth`` is a
      soft, possibly transient failure (e.g. token rotated mid-flight);
      ``auth_permanent`` means the key is definitively invalid and the
      operator has to intervene.
    * **billing** – provider-side credit exhaustion (HTTP 402 / 403 with
      billing sub-code).  Recovery is: rotate to a different project /
      provider, never retry on the same credential.
    * **rate_limit / upstream_rate_limit** – 429 variants.  The first is
      a direct provider throttle, the second is a 429 surfaced via a
      gateway (OpenRouter, ...) that wraps an upstream provider error.
    * **overloaded / server_error** – 503/529/500/502 style failures.
      Transient, always retry with backoff; ``overloaded`` additionally
      hints that a longer cool-down is appropriate.
    * **timeout** – connection / read / deadline failures.
    * **context_overflow / payload_too_large** – the request itself is
      too large.  Recovery is compress or shrink the payload, never
      blind retry.
    * **model_not_found / provider_policy_blocked / content_policy_blocked**
      – model/policy errors that require a model/provider swap.
    * **format_error** – 400 / validation errors.  Usually a caller bug
      (prompt, schema, tool-call format) – not retryable.
    * **ssl_cert_verification** – TLS certificate issues, not retryable
      without human intervention.
    * **image_too_large** – multimodal image dimension / byte limit.
    * **unknown** – catch-all for anything we cannot categorise.
    """

    # Authentication / authorization
    auth = "auth"
    auth_permanent = "auth_permanent"

    # Billing / quota
    billing = "billing"

    # Rate limiting
    rate_limit = "rate_limit"
    upstream_rate_limit = "upstream_rate_limit"

    # Server-side
    overloaded = "overloaded"
    server_error = "server_error"

    # Transport
    timeout = "timeout"

    # Context / payload
    context_overflow = "context_overflow"
    payload_too_large = "payload_too_large"

    # Model / policy
    model_not_found = "model_not_found"
    provider_policy_blocked = "provider_policy_blocked"
    content_policy_blocked = "content_policy_blocked"

    # Request format
    format_error = "format_error"

    # TLS
    ssl_cert_verification = "ssl_cert_verification"

    # Multimodal
    image_too_large = "image_too_large"

    # Catch-all
    unknown = "unknown"


# ──────────────────────────────────────────────────────────────────────
# 2. ClassifiedError dataclass
# ──────────────────────────────────────────────────────────────────────


@dataclass
class ClassifiedError:
    """Structured description of an API failure plus recovery hints.

    All boolean flags are defaults for the *first* recovery attempt;
    higher-level orchestrators (the LLM retry loop, the failover
    governor, …) combine them with their own state (attempt number,
    provider budget, …) to decide the exact action.
    """

    reason: FailoverReason
    message: str = ""
    should_retry: bool = False
    should_rotate_credential: bool = False
    should_fallback_model: bool = False
    should_compress: bool = False
    http_status: Optional[int] = None
    provider_hint: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)


# ──────────────────────────────────────────────────────────────────────
# 4. Internal extraction helpers
# ──────────────────────────────────────────────────────────────────────


def _extract_status_code(error: Exception) -> Optional[int]:
    """Pull an HTTP status code off an exception using several heuristics.

    Async clients differ a lot in how they expose status codes:
    ``httpx`` uses ``.status_code``, ``aiohttp`` uses ``.code``, some
    provider SDKs stuff the code into ``.http_status``, and some just
    embed it in the message text.  We try all of them in order and
    finally regex-scan the error string as a last resort.
    """
    for attr in ("status_code", "http_status", "code", "status"):
        val = getattr(error, attr, None)
        if isinstance(val, int) and 100 <= val <= 599:
            return val
    m = re.search(r"\b([45]\d{2})\b", str(error))
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            return None
    return None


def _extract_error_body(error: Exception) -> Any:
    """Extract the decoded error body (dict or str) if the exception has one."""
    for attr in ("body", "response", "error"):
        val = getattr(error, attr, None)
        if isinstance(val, (dict, str, list)):
            if isinstance(val, str):
                try:
                    parsed = json.loads(val)
                    if isinstance(parsed, dict):
                        return parsed
                except (json.JSONDecodeError, TypeError):
                    return {"message": val}
            return val
    return {}


def _extract_error_code(body: Any) -> str:
    """Best-effort extraction of the provider's structured error code."""
    if not isinstance(body, dict):
        return ""
    err = body.get("error", body)
    if isinstance(err, dict):
        return str(err.get("code", "") or "")
    return ""


def _compose_error_text(error: Exception, body: Any) -> str:
    """Build a single, lower-cased search string for pattern matching."""
    parts: list[str] = [str(error).lower()]

    if isinstance(body, dict):
        err_obj = body.get("error", {})
        if isinstance(err_obj, dict):
            body_msg = str(err_obj.get("message") or "").lower()
            if body_msg and body_msg not in parts[0]:
                parts.append(body_msg)
            metadata = err_obj.get("metadata", {})
            if isinstance(metadata, dict):
                raw = metadata.get("raw") or ""
                if isinstance(raw, str) and raw.strip():
                    try:
                        inner = json.loads(raw)
                        if isinstance(inner, dict):
                            inner_err = inner.get("error", {})
                            if isinstance(inner_err, dict):
                                inner_msg = str(inner_err.get("message") or "").lower()
                                if inner_msg and inner_msg not in parts[0] and inner_msg not in body_msg:
                                    parts.append(inner_msg)
                    except (json.JSONDecodeError, TypeError):
                        pass
        elif body.get("message"):
            body_msg = str(body.get("message") or "").lower()
            if body_msg and body_msg not in parts[0]:
                parts.append(body_msg)

    return " ".join(parts)


def _human_message(error: Exception, body: Any) -> str:
    msg = str(error)[:500]
    if isinstance(body, dict):
        err_obj = body.get("error", body)
        if isinstance(err_obj, dict):
            body_msg = err_obj.get("message")
            if body_msg and str(body_msg) not in msg:
                msg = f"{msg} | {str(body_msg)[:200]}"
    return msg


def _is_openrouter_upstream_error(body: Any, provider: str) -> bool:
    """OpenRouter wraps upstream 429s with a distinctive message shape."""
    if provider != "openrouter":
        return False
    if not isinstance(body, dict):
        return False
    err = body.get("error", {})
    if not isinstance(err, dict):
        return False
    text = str(err.get("message", "")).lower()
    return "provider returned error" in text


def _upstream_provider(body: Any) -> Optional[str]:
    if not isinstance(body, dict):
        return None
    err = body.get("error", {})
    if not isinstance(err, dict):
        return None
    metadata = err.get("metadata", {})
    if not isinstance(metadata, dict):
        return None
    value = metadata.get("upstream")
    if value is None:
        return None
    return str(value)


# ──────────────────────────────────────────────────────────────────────
# 5. Public classification API
# ──────────────────────────────────────────────────────────────────────


def classify_api_error(
    error: Exception,
    http_status: Optional[int] = None,
    provider: Optional[str] = None,
) -> ClassifiedError:
    """Classify an API-level exception into a :class:`ClassifiedError`.

    The classifier walks a priority-ordered pipeline (provider-specific
    patterns → HTTP status → error-code → message patterns → transport
    heuristics → catch-all).  It accepts both the raw exception and
    optional ``http_status`` / ``provider`` hints supplied by the
    caller so sync and async transports can share the exact same
    behaviour.

    Parameters
    ----------
    error:
        The raised exception.  Any type is accepted – the classifier
        inspects ``status_code`` / ``http_status`` / ``code`` /
        ``body`` / ``response`` attributes reflectively.
    http_status:
        Optional pre-extracted HTTP status.  When provided it takes
        precedence over introspection (useful for async transports
        that already unwrapped the status).
    provider:
        Optional provider identifier (e.g. ``"openrouter"``,
        ``"anthropic"``, ``"ollama"``).  Used to disambiguate
        provider-specific error bodies.

    Returns
    -------
    ClassifiedError
        Always returns a non-``None`` structure with at least
        ``reason == FailoverReason.unknown``.
    """

    status_code = http_status if http_status is not None else _extract_status_code(error)
    error_type = type(error).__name__
    body = _extract_error_body(error)
    error_code = _extract_error_code(body)
    error_msg = _compose_error_text(error, body)
    provider_lower = (provider or "").strip().lower()

    def _result(
        reason: FailoverReason,
        *,
        should_retry: bool = False,
        should_rotate_credential: bool = False,
        should_fallback_model: bool = False,
        should_compress: bool = False,
        provider_hint: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> ClassifiedError:
        return ClassifiedError(
            reason=reason,
            message=_human_message(error, body),
            should_retry=should_retry,
            should_rotate_credential=should_rotate_credential,
            should_fallback_model=should_fallback_model,
            should_compress=should_compress,
            http_status=status_code,
            provider_hint=provider_hint or provider,
            extra=extra or {},
        )

    # ── 1. Provider-specific / high-signal patterns (highest priority) ──

    if any(p in error_msg for p in _CONTENT_POLICY_BLOCKED_PATTERNS):
        return _result(
            FailoverReason.content_policy_blocked,
            should_retry=False,
            should_fallback_model=True,
        )

    # ── 2. HTTP status code driven classification ───────────────────────

    if status_code is not None:
        # 401 / 407 – auth failure, usually rotate the key
        if status_code in {401, 407}:
            permanent_signals = (
                "expired",
                "revoked",
                "deleted",
                "disabled",
                "incorrect api key",
                "invalid api key",
                "invalid_token",
                "api key not found",
            )
            is_permanent = any(s in error_msg for s in permanent_signals)
            return _result(
                FailoverReason.auth_permanent if is_permanent else FailoverReason.auth,
                should_retry=False,
                should_rotate_credential=True,
                should_fallback_model=True,
            )

        # 403 – either billing (spend limit) or authorization
        if status_code == 403:
            if any(p in error_msg for p in _BILLING_PATTERNS):
                return _result(
                    FailoverReason.billing,
                    should_retry=False,
                    should_fallback_model=True,
                )
            return _result(
                FailoverReason.auth,
                should_retry=False,
                should_fallback_model=True,
            )

        # 402 – payment required
        if status_code == 402:
            return _result(
                FailoverReason.billing,
                should_retry=False,
                should_fallback_model=True,
            )

        # 404 – model not found / provider policy
        if status_code == 404:
            if any(p in error_msg for p in _MODEL_NOT_FOUND_PATTERNS):
                return _result(
                    FailoverReason.model_not_found,
                    should_retry=False,
                    should_fallback_model=True,
                )
            if any(p in error_msg for p in _PROVIDER_POLICY_BLOCKED_PATTERNS):
                return _result(
                    FailoverReason.provider_policy_blocked,
                    should_retry=False,
                )
            if any(p in error_msg for p in _BILLING_PATTERNS):
                return _result(
                    FailoverReason.billing,
                    should_retry=False,
                    should_fallback_model=True,
                )
            return _result(
                FailoverReason.unknown,
                should_retry=True,
            )

        # 413 – payload too large
        if status_code == 413:
            return _result(
                FailoverReason.payload_too_large,
                should_retry=True,
                should_compress=True,
            )

        # 429 – rate limit / overload / upstream
        if status_code == 429:
            if any(p in error_msg for p in _OVERLOADED_PATTERNS):
                return _result(
                    FailoverReason.overloaded,
                    should_retry=True,
                )
            if _is_openrouter_upstream_error(body, provider_lower):
                upstream = _upstream_provider(body)
                extra = {"upstream_provider": upstream} if upstream else {}
                return _result(
                    FailoverReason.upstream_rate_limit,
                    should_retry=True,
                    should_fallback_model=True,
                    provider_hint=upstream or provider,
                    extra=extra,
                )
            return _result(
                FailoverReason.rate_limit,
                should_retry=True,
                should_fallback_model=True,
            )

        # 400 – format / context / image
        if status_code == 400:
            if any(p in error_msg for p in _IMAGE_TOO_LARGE_PATTERNS):
                return _result(
                    FailoverReason.image_too_large,
                    should_retry=True,
                    should_compress=True,
                )
            if any(p in error_msg for p in _CONTEXT_OVERFLOW_PATTERNS):
                return _result(
                    FailoverReason.context_overflow,
                    should_retry=True,
                    should_compress=True,
                )
            if any(p in error_msg for p in _FORMAT_ERROR_PATTERNS):
                return _result(
                    FailoverReason.format_error,
                    should_retry=False,
                    should_fallback_model=True,
                )
            if any(p in error_msg for p in _MODEL_NOT_FOUND_PATTERNS):
                return _result(
                    FailoverReason.model_not_found,
                    should_retry=False,
                    should_fallback_model=True,
                )
            return _result(
                FailoverReason.format_error,
                should_retry=False,
            )

        # 500 / 502 – server error, but watch for context overflow
        if status_code in {500, 502}:
            if any(p in error_msg for p in _FORMAT_ERROR_PATTERNS):
                return _result(
                    FailoverReason.format_error,
                    should_retry=False,
                    should_fallback_model=True,
                )
            if any(p in error_msg for p in _CONTEXT_OVERFLOW_PATTERNS):
                return _result(
                    FailoverReason.context_overflow,
                    should_retry=True,
                    should_compress=True,
                )
            return _result(
                FailoverReason.server_error,
                should_retry=True,
            )

        # 503 / 529 – overloaded
        if status_code in {503, 529}:
            if any(p in error_msg for p in _CONTEXT_OVERFLOW_PATTERNS):
                return _result(
                    FailoverReason.context_overflow,
                    should_retry=True,
                    should_compress=True,
                )
            return _result(
                FailoverReason.overloaded,
                should_retry=True,
            )

        # 408 / 499 – timeout
        if status_code == 408:
            return _result(FailoverReason.timeout, should_retry=True)

    # ── 3. Error code classification ────────────────────────────────────

    if error_code:
        code_lower = error_code.lower()
        if code_lower in {"invalid_request_error", "unknown_parameter", "unsupported_parameter"}:
            return _result(FailoverReason.format_error, should_retry=False)
        if code_lower in {"insufficient_quota", "billing_not_active", "payment_required"}:
            return _result(
                FailoverReason.billing,
                should_retry=False,
                should_fallback_model=True,
            )
        if code_lower in {"content_policy_violation", "policy_violation"}:
            return _result(
                FailoverReason.content_policy_blocked,
                should_retry=False,
                should_fallback_model=True,
            )

    # ── 4. Message pattern matching (no status code) ────────────────────

    if any(p in error_msg for p in _CONTEXT_OVERFLOW_PATTERNS):
        return _result(
            FailoverReason.context_overflow,
            should_retry=True,
            should_compress=True,
        )

    if any(p in error_msg for p in _BILLING_PATTERNS):
        return _result(
            FailoverReason.billing,
            should_retry=False,
            should_fallback_model=True,
        )

    if any(p in error_msg for p in _RATE_LIMIT_PATTERNS):
        return _result(
            FailoverReason.rate_limit,
            should_retry=True,
            should_fallback_model=True,
        )

    if any(p in error_msg for p in _OVERLOADED_PATTERNS):
        return _result(FailoverReason.overloaded, should_retry=True)

    if any(p in error_msg for p in _MODEL_NOT_FOUND_PATTERNS):
        return _result(
            FailoverReason.model_not_found,
            should_retry=False,
            should_fallback_model=True,
        )

    if any(p in error_msg for p in _PAYLOAD_TOO_LARGE_PATTERNS):
        return _result(
            FailoverReason.payload_too_large,
            should_retry=True,
            should_compress=True,
        )

    if any(p in error_msg for p in _IMAGE_TOO_LARGE_PATTERNS):
        return _result(
            FailoverReason.image_too_large,
            should_retry=True,
            should_compress=True,
        )

    if any(p in error_msg for p in _AUTH_PATTERNS):
        return _result(
            FailoverReason.auth,
            should_retry=True,
            should_rotate_credential=True,
            should_fallback_model=True,
        )

    if any(p in error_msg for p in _FORMAT_ERROR_PATTERNS):
        return _result(FailoverReason.format_error, should_retry=False)

    if any(p in error_msg for p in _PROVIDER_POLICY_BLOCKED_PATTERNS):
        return _result(
            FailoverReason.provider_policy_blocked,
            should_retry=False,
        )

    if any(p in error_msg for p in _CONTENT_POLICY_BLOCKED_PATTERNS):
        return _result(
            FailoverReason.content_policy_blocked,
            should_retry=False,
            should_fallback_model=True,
        )

    if "timed out" in error_msg or "deadline exceeded" in error_msg or "timeout" in error_msg:
        return _result(FailoverReason.timeout, should_retry=True)

    # ── 5. SSL certificate verification (fail fast) ──────────────────────

    if any(p in error_msg for p in _SSL_CERT_VERIFY_PATTERNS):
        return _result(
            FailoverReason.ssl_cert_verification,
            should_retry=False,
        )

    # ── 6. Transport / timeout heuristics ────────────────────────────────

    if error_type in _TRANSPORT_ERROR_TYPES or isinstance(
        error, (TimeoutError, ConnectionError, OSError)
    ):
        return _result(FailoverReason.timeout, should_retry=True)

    # ── 7. Fallback ──────────────────────────────────────────────────────

    return _result(FailoverReason.unknown, should_retry=True)


# ──────────────────────────────────────────────────────────────────────
# 6. Helper utilities
# ──────────────────────────────────────────────────────────────────────


def is_retryable(classified: ClassifiedError) -> bool:
    """Return ``True`` when a retry with the same configuration makes sense.

    This is a thin wrapper around ``classified.should_retry`` that the
    retry-loop can consume uniformly (it keeps the door open for
    future heuristics that combine multiple flags, e.g. retrying only
    after a backoff window).
    """

    return classified.should_retry


def is_local_processing_error(error: Exception) -> bool:
    """Return ``True`` for *deterministic local* errors that must not be retried.

    The heuristic looks for messages that strongly indicate a bug in
    our request-building / transport glue (``TypeError: object of type
    'NoneType' is not JSON serializable``, ...) versus a genuine
    upstream failure (rate-limit, timeout, ...).  Catching these early
    avoids wasting provider quota on retries that can never succeed.

    The function is intentionally conservative – a false positive
    (marking a transient API error as local) is worse than a false
    negative (retrying a local bug once).
    """

    error_type = type(error).__name__
    msg = str(error).lower()

    if error_type in _TRANSPORT_ERROR_TYPES:
        return False
    if isinstance(error, (TimeoutError, ConnectionError, OSError)):
        return False

    if not any(p in msg for p in _LOCAL_PROCESSING_ERROR_PATTERNS):
        return False

    # TLS / certificate failures are not local processing bugs
    if any(p in msg for p in _SSL_CERT_VERIFY_PATTERNS):
        return False

    # If it looks like an HTTP status-bearing error it is definitely
    # not a local processing bug (we would never have reached the
    # network otherwise).
    if _extract_status_code(error) is not None:
        return False

    return True
